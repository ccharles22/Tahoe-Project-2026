"""Flask Blueprint for file upload and parsing endpoints.

This blueprint provides a `/parsing/health` endpoint and a `/parsing/upload`
POST endpoint that accepts TSV/CSV/JSON experiment files, runs the
project parsers and QC, and optionally persists parsed records to the DB.

The implementation uses a temporary file for uploads and ensures cleanup
and transactional DB commits/rollbacks.
"""

import os
import tempfile
import json
import logging
from typing import Optional, Tuple

from flask import request, jsonify, render_template, redirect, url_for, flash, Response, session as flask_session
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from app.extensions import db
from app.models import Experiment
from app.services.parsing.tsv_parser import TSVParser
from app.services.parsing.json_parser import JSONParser
from app.services.parsing.qc import QualityControl
from app.services.parsing.base_parser import BaseParser
from app.services.parsing.utils import safe_int, safe_float
from app.services.parsing.db_operations import batch_upsert_variants

from . import parsing_bp

# Configure logging
logger = logging.getLogger(__name__)


# Allowed file extensions
ALLOWED_EXTENSIONS = {'.tsv', '.csv', '.json'}

# Max file size (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024


def allowed_file(filename: str) -> bool:
    """
    Check if filename has an allowed extension.
    
    Args:
        filename: Name of the file
        
    Returns:
        True if allowed, False otherwise
    """
    if not filename or '.' not in filename:
        return False
    
    # Get extension (lowercase)
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def get_parser(filepath: str) -> BaseParser:
    """
    Get appropriate parser based on file extension.
    
    Args:
        filepath: Path to file
        
    Returns:
        Parser instance (TSVParser or JSONParser)
    """
    ext = os.path.splitext(filepath)[1].lower()
    
    if ext in ['.tsv', '.csv']:
        return TSVParser(filepath)
    elif ext == '.json':
        return JSONParser(filepath)
    else:
        raise ValueError(f"Unsupported file extension: {ext}")


def get_experiment_ids() -> list[int]:
    """Get list of distinct experiment IDs from database."""
    try:
        result = db.session.query(Experiment.experiment_id).order_by(Experiment.experiment_id).all()
        return [row[0] for row in result if row[0] is not None]
    except Exception:
        return []


@parsing_bp.route('/health', methods=['GET'])
def health() -> Tuple[Response, int]:
    """Health check endpoint."""
    return jsonify({'status': 'ok'}), 200


@parsing_bp.route('/upload', methods=['GET'])
def upload_form() -> str:
    """Render upload form page."""
    experiment_ids = get_experiment_ids()
    selected_experiment = request.args.get('experiment_id', type=int)
    return render_template(
        'parsing/upload.html',
        experiment_ids=experiment_ids,
        selected_experiment=selected_experiment
    )


@parsing_bp.route('/upload/submit', methods=['POST'])
def upload_form_submit() -> str:
    """
    Handle form upload submission.
    If the request came from the staging workflow (has 'from_staging' or
    referrer contains '/staging'), store results in session and redirect back.
    Otherwise render the standalone results page.
    """
    temp_filepath: Optional[str] = None
    session = None

    # Determine experiment_id from form
    experiment_id = request.form.get('experiment_id', type=int)
    if not experiment_id:
        experiment_id = request.form.get('new_experiment_id', type=int)
    if not experiment_id:
        experiment_id = 1  # Default

    # Detect if request came from the staging workflow
    from_staging = bool(request.form.get('from_staging')) or (
        request.referrer and '/staging' in request.referrer
    )

    def _save_and_redirect(result_dict):
        """Store parsing result in session and redirect back to staging."""
        key = f"parsing_result_{experiment_id}"
        flask_session[key] = result_dict
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
        ))

    try:
        # Check if file is present
        if 'file' not in request.files:
            if from_staging:
                flash('No file provided', 'error')
                return redirect(url_for('staging.create_experiment', experiment_id=experiment_id))
            flash('No file provided', 'error')
            return redirect(url_for('parsing.upload_form'))

        file = request.files['file']

        # Check if filename is empty
        if file.filename == '':
            if from_staging:
                flash('No file selected', 'error')
                return redirect(url_for('staging.create_experiment', experiment_id=experiment_id))
            flash('No file selected', 'error')
            return redirect(url_for('parsing.upload_form'))

        # Validate file extension
        if not allowed_file(file.filename):
            if from_staging:
                flash(f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
                return redirect(url_for('staging.create_experiment', experiment_id=experiment_id))
            flash(f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
            return redirect(url_for('parsing.upload_form'))

        # Secure filename
        filename = secure_filename(file.filename)

        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
        temp_filepath = temp_file.name
        temp_file.close()

        file.save(temp_filepath)

        # Check file size
        file_size = os.path.getsize(temp_filepath)
        if file_size > MAX_FILE_SIZE:
            if from_staging:
                flash(f'File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB', 'error')
                return redirect(url_for('staging.create_experiment', experiment_id=experiment_id))
            flash(f'File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB', 'error')
            return redirect(url_for('parsing.upload_form'))

        # Parse file
        parser = get_parser(temp_filepath)
        parse_success = parser.parse()

        if not parse_success:
            result = {
                'success': False,
                'error_message': 'Parsing failed',
                'errors': parser.errors[:20],
                'warnings': parser.warnings[:20],
            }
            if from_staging:
                return _save_and_redirect(result)
            return render_template(
                'parsing/upload_results.html',
                experiment_id=experiment_id, **result
            )

        # Run QC validation (dataset-adaptive thresholds)
        qc = QualityControl(percentile_mode=True)
        parser.validate_all(qc)

        # Check for critical errors
        if parser.errors:
            result = {
                'success': False,
                'error_message': 'Validation failed',
                'errors': parser.errors[:20],
                'warnings': parser.warnings[:20],
            }
            if from_staging:
                return _save_and_redirect(result)
            return render_template(
                'parsing/upload_results.html',
                experiment_id=experiment_id, **result
            )

        # Store in database using batch upsert
        session = db.session
        inserted_count, updated_count = batch_upsert_variants(
            session, parser.records, experiment_id, parser.extract_metadata
        )
        session.commit()

        summary = parser.get_summary()
        flash('File uploaded and processed successfully!', 'success')

        result = {
            'success': True,
            'total_records': summary['total_records'],
            'inserted_count': inserted_count,
            'updated_count': updated_count,
            'warnings': parser.warnings[:20],
            'warnings_count': len(parser.warnings),
            'detected_fields': summary['detected_fields'],
            'errors': [],
        }
        if from_staging:
            return _save_and_redirect(result)
        return render_template(
            'parsing/upload_results.html',
            experiment_id=experiment_id, **result
        )

    except Exception as e:
        try:
            if session is not None:
                session.rollback()
        except Exception:
            pass

        result = {
            'success': False,
            'error_message': f'Database error: {str(e)}',
            'errors': [str(e)],
            'warnings': [],
        }
        if from_staging:
            return _save_and_redirect(result)
        return render_template(
            'parsing/upload_results.html',
            experiment_id=experiment_id, **result
        )

    finally:
        if session:
            db.session.remove()

        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.unlink(temp_filepath)
            except Exception:
                pass


@parsing_bp.route('/upload', methods=['POST'])
def upload() -> Tuple[Response, int]:
    """
    Upload and parse experimental data file.
    
    Accepts:
        - file: TSV, CSV, or JSON file (multipart/form-data)
        - experiment_id: Integer experiment ID (optional, default=1)
        - persist_thresholds: Boolean for percentile mode (optional, default=False)
        
    Returns:
        JSON response with parsing results and HTTP status code
    """
    temp_filepath: Optional[str] = None
    session = None
    
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        # Check if filename is empty
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        # Validate file extension
        if not allowed_file(file.filename):
            return jsonify({
                'error': f'Invalid file extension. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400
        
        # Get optional parameters
        experiment_id = request.form.get('experiment_id', 1, type=int)
        persist_thresholds = request.form.get('persist_thresholds', 'false').lower() == 'true'
        
        # Secure filename
        filename = secure_filename(file.filename)
        
        # Save to temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1])
        temp_filepath = temp_file.name
        temp_file.close()
        
        file.save(temp_filepath)
        
        # Check file size
        file_size = os.path.getsize(temp_filepath)
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                'error': f'File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024:.0f} MB'
            }), 400
        
        # Parse file
        parser = get_parser(temp_filepath)
        parse_success = parser.parse()
        
        if not parse_success:
            return jsonify({
                'error': 'Parsing failed',
                'details': parser.errors
            }), 400
        
        # Run QC validation (dataset-adaptive thresholds)
        qc = QualityControl(percentile_mode=True)
        parser.validate_all(qc)
        
        # Check for critical errors
        if parser.errors:
            return jsonify({
                'error': 'Validation failed',
                'errors': parser.errors,
                'warnings': parser.warnings
            }), 400
        
        # Store in database using batch upsert
        session = db.session
        inserted_count, updated_count = batch_upsert_variants(
            session, parser.records, experiment_id, parser.extract_metadata
        )
        session.commit()
        
        # Return success response
        summary = parser.get_summary()
        return jsonify({
            'success': True,
            'total_records': summary['total_records'],
            'inserted_count': inserted_count,
            'updated_count': updated_count,
            'warnings': parser.warnings,
            'warnings_count': len(parser.warnings),
            'detected_fields': summary['detected_fields']
        }), 200
        
    except Exception as e:
        # Log the exception and rollback
        logger.error(f"Upload error: {repr(e)}", exc_info=True)

        # Rollback on error (best-effort)
        try:
            if session is not None:
                session.rollback()
        except Exception:
            pass

        return jsonify({
            'error': 'Database error',
            'details': repr(e)
        }), 500
        
    finally:
        # Clean up
        if session:
            db.session.remove()
        
        # Delete temporary file
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.unlink(temp_filepath)
            except Exception:
                pass  # Ignore cleanup errors
