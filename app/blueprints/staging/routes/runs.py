"""Analysis and sequence execution endpoints for staging."""

import time
import traceback

from flask import current_app, redirect, request, url_for
from flask_login import login_required

from app.services.staging.analysis_runtime import run_analysis_for_experiment
from app.services.staging.session_state import (
    get_sequence_status_from_session,
    save_sequence_status_to_session,
)

from .. import staging_bp


_SEQUENCE_REUSE_WINDOW_S = 300


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


def _should_reuse_recent_sequence_run(experiment_id: int) -> bool:
    """Return True when a just-completed Step 4 run can be reused safely."""
    status = get_sequence_status_from_session(experiment_id) or {}
    if str(status.get('status', '')).lower() != 'success':
        return False

    completed_at = status.get('completed_at_epoch')
    try:
        completed_at_int = int(completed_at)
    except (TypeError, ValueError):
        return False

    return (int(time.time()) - completed_at_int) <= _SEQUENCE_REUSE_WINDOW_S


@staging_bp.post('/analysis/run')
@login_required
def run_analysis():
    """Run sequence processing first, then analysis, and redirect back to staging."""
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    if _should_reuse_recent_sequence_run(exp_id_int):
        seq_ok = True
        sequence_message = 'Sequence processing already completed recently. Reusing latest mutation outputs.'
    else:
        seq_ok, sequence_message = _run_sequence_processing_for_experiment(exp_id_int)
    if not seq_ok:
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id,
                sequence_message=sequence_message,
                analysis_message='Analysis skipped because sequence processing failed.',
            )
        )

    ok, analysis_message = run_analysis_for_experiment(exp_id_int, current_app._get_current_object())
    if not ok and not analysis_message:
        analysis_message = 'Analysis failed.'

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            sequence_message=sequence_message,
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
