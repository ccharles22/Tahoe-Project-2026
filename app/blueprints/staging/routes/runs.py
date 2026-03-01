"""Analysis and sequence execution endpoints for staging."""

import time
import traceback

from flask import current_app, redirect, request, url_for
from flask_login import login_required
from sqlalchemy import text

from app.extensions import db
from app.services.staging.analysis_runtime import run_analysis_for_experiment
from app.services.staging.session_state import (
    save_sequence_status_to_session,
)

from .. import staging_bp


def _run_sequence_processing_for_experiment(experiment_id: int) -> tuple[bool, str]:
    """Run sequence processing synchronously and persist UI status text."""
    try:
        from app.jobs.run_sequence_processing import run_sequence_processing

        # These staging actions are explicitly about refreshing downstream
        # mutation-aware outputs, so always force a full reprocess.
        run_sequence_processing(experiment_id, force_reprocess=True)
        message = 'Sequence processing completed. Mutation outputs were refreshed in the database.'
        save_sequence_status_to_session(
            experiment_id,
            {
                'status': 'success',
                'summary': message,
                'technical_details': '',
                'completed_at_epoch': int(time.time()),
            },
        )
        return True, message
    except Exception as exc:
        message = f'Sequence processing failed: {exc}'
        save_sequence_status_to_session(
            experiment_id,
            {
                'status': 'failed',
                'summary': str(exc),
                'technical_details': traceback.format_exc(),
            },
        )
        return False, message


def _has_sequence_outputs(experiment_id: int) -> bool:
    """Return True when sequence processing has already persisted results."""
    try:
        count = db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM variant_sequence_analysis
                WHERE experiment_id = :eid
                """
            ),
            {'eid': experiment_id},
        ).scalar()
        return int(count or 0) > 0
    except Exception:
        db.session.rollback()
        return False


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


@staging_bp.post('/sequence/run')
@login_required
def run_sequence():
    """Run sequence processing for the experiment and return status via redirect."""
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    _, message = _run_sequence_processing_for_experiment(exp_id_int)

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))
