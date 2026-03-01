"""Analysis and sequence execution endpoints for staging."""

import time
import traceback

from flask import current_app, jsonify, redirect, request, url_for
from flask_login import login_required
from sqlalchemy import text

from app.extensions import db
from app.jobs.run_sequence_processing import submit_sequence_processing
from app.services.staging.analysis_runtime import run_analysis_for_experiment
from app.services.staging.session_state import (
    is_sequence_reprocess_required,
    save_sequence_status_to_session,
)

from .. import staging_bp


def _get_experiment_analysis_status(experiment_id: int) -> str:
    """Return the persisted experiment analysis status."""
    status = db.session.execute(
        text(
            """
            SELECT analysis_status
            FROM public.experiments
            WHERE experiment_id = :eid
            """
        ),
        {'eid': experiment_id},
    ).scalar()
    return str(status or '').strip().upper()


def _has_persisted_sequence_outputs(experiment_id: int) -> bool:
    """Return True when all variants for the experiment have sequence rows."""
    try:
        counts = db.session.execute(
            text(
                """
                SELECT
                  COUNT(DISTINCT v.variant_id) AS total_variants,
                  COUNT(DISTINCT CASE WHEN vsa.vsa_id IS NOT NULL THEN v.variant_id END) AS analysed_variants
                FROM public.variants v
                JOIN public.generations g
                  ON g.generation_id = v.generation_id
                LEFT JOIN public.variant_sequence_analysis vsa
                  ON vsa.variant_id = v.variant_id
                WHERE g.experiment_id = :eid
                """
            ),
            {'eid': experiment_id},
        ).mappings().one()
        total_variants = int(counts['total_variants'] or 0)
        analysed_variants = int(counts['analysed_variants'] or 0)
        return total_variants > 0 and analysed_variants >= total_variants
    except Exception:
        db.session.rollback()
        return False


def _has_sequence_outputs(experiment_id: int) -> bool:
    """Return True when sequence outputs exist and are not marked stale."""
    if is_sequence_reprocess_required(experiment_id):
        return False
    return _has_persisted_sequence_outputs(experiment_id)


def _sequence_status_payload(experiment_id: int) -> tuple[dict, int]:
    """Summarise current sequence-processing state for polling clients."""
    persisted_status = _get_experiment_analysis_status(experiment_id)
    if persisted_status == 'ANALYSIS_RUNNING':
        return {
            'state': 'running',
            'message': 'Sequence processing is still running.',
        }, 202
    if persisted_status == 'FAILED':
        return {
            'state': 'failed',
            'message': 'Sequence processing failed.',
        }, 200
    if _has_persisted_sequence_outputs(experiment_id):
        return {
            'state': 'completed',
            'message': 'Sequence processing completed.',
        }, 200
    return {
        'state': 'pending',
        'message': 'Sequence processing has not completed yet.',
    }, 200


@staging_bp.post('/analysis/run')
@login_required
def run_analysis():
    """Run analysis only when sequence outputs already exist."""
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    if not _has_sequence_outputs(exp_id_int):
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id,
                analysis_message='Run sequence processing first. Analysis only generates plots and reports from existing sequence outputs.',
            )
        )

    ok, analysis_message = run_analysis_for_experiment(exp_id_int, current_app._get_current_object())
    if not ok and not analysis_message:
        analysis_message = 'Analysis failed.'

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            analysis_message=analysis_message,
        )
    )


@staging_bp.get('/sequence/status/<int:experiment_id>')
@login_required
def sequence_status_json(experiment_id: int):
    """Return JSON status for the current sequence-processing run."""
    payload, status_code = _sequence_status_payload(experiment_id)
    return jsonify(payload), status_code


@staging_bp.post('/sequence/run')
@login_required
def run_sequence():
    """Launch sequence processing in the background and return immediately."""
    experiment_id = request.form.get('experiment_id', '').strip()
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not experiment_id.isdigit():
        if is_xhr:
            return jsonify({'state': 'failed', 'message': 'Missing experiment_id.'}), 400
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    explicit_force = request.form.get('force_reprocess', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    force_reprocess = explicit_force or is_sequence_reprocess_required(exp_id_int)
    if not force_reprocess and _has_sequence_outputs(exp_id_int):
        message = 'Sequence outputs are already up to date. Reusing existing mutation results.'
        save_sequence_status_to_session(
            exp_id_int,
            {
                'status': 'success',
                'summary': message,
                'technical_details': '',
                'completed_at_epoch': int(time.time()),
            },
        )
        if is_xhr:
            return jsonify({'state': 'completed', 'message': message}), 200
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id,
                sequence_message=message,
            )
        )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'state': 'completed', 'message': message}), 200

    try:
        current_status = _get_experiment_analysis_status(exp_id_int)
        if current_status == 'ANALYSIS_RUNNING':
            message = 'Sequence processing is already running in the background.'
            save_sequence_status_to_session(
                exp_id_int,
                {
                    'status': 'running',
                    'summary': message,
                    'technical_details': '',
                    'completed_at_epoch': int(time.time()),
                },
            )
            if is_xhr:
                return jsonify({'state': 'running', 'message': message}), 202
            return redirect(
                url_for(
                    'staging.create_experiment',
                    experiment_id=experiment_id,
                    sequence_message=message,
                )
            )
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'state': 'running', 'message': message}), 202

        submit_sequence_processing(exp_id_int, force_reprocess=force_reprocess)
        if force_reprocess:
            message = (
                'Sequence processing started in the background. A full refresh is '
                'running because the experiment inputs changed.'
            )
        else:
            message = (
                'Sequence processing started in the background. This page will show '
                'updated sequence outputs when the run finishes.'
            )
        save_sequence_status_to_session(
            exp_id_int,
            {
                'status': 'running',
                'summary': message,
                'technical_details': '',
                'completed_at_epoch': int(time.time()),
            },
        )
    except Exception as exc:
        message = f'Sequence processing failed: {exc}'
        save_sequence_status_to_session(
            exp_id_int,
            {
                'status': 'failed',
                'summary': str(exc),
                'technical_details': traceback.format_exc(),
            },
        )
        if is_xhr:
            return jsonify({'state': 'failed', 'message': message}), 500

    if is_xhr:
        return jsonify({'state': 'running', 'message': message}), 202

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))
