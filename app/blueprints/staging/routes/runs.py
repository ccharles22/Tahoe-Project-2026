"""Analysis and sequence execution endpoints for staging."""

import threading
import traceback

from flask import current_app, redirect, request, url_for
from flask_login import login_required

from app.services.staging.analysis_runtime import run_analysis_background
from app.services.staging.session_state import save_sequence_status_to_session

from .. import staging_bp


@staging_bp.post('/analysis/run')
@login_required
def run_analysis():
    """Trigger analysis in a background thread and redirect back to staging."""
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    app_obj = current_app._get_current_object()
    t = threading.Thread(
        target=run_analysis_background,
        args=(exp_id_int, app_obj),
        daemon=True,
        name=f"analysis-exp-{exp_id_int}",
    )
    t.start()
    analysis_message = 'Analysis started in background. Refresh in a moment to see outputs.'

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
    try:
        from app.jobs.sequence.run_sequence_processing import run_sequence_processing

        run_sequence_processing(exp_id_int)
        message = 'Sequence processing completed. Outputs are stored in the database.'
        save_sequence_status_to_session(
            exp_id_int,
            {
                'status': 'success',
                'summary': message,
                'technical_details': '',
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

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))
