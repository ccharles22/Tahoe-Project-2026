"""Analysis and sequence execution endpoints for staging."""

import traceback

from flask import current_app, redirect, request, url_for
from flask_login import login_required

from app.services.staging.analysis_runtime import run_analysis_for_experiment
from app.services.staging.session_state import save_sequence_status_to_session

from .. import staging_bp


@staging_bp.post('/analysis/run')
@login_required
def run_analysis():
    """Run analysis for the experiment and redirect back to staging."""
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
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
    try:
        from app.jobs.run_sequence_processing import run_sequence_processing

        # This action is explicitly for computing/refreshing mutation outputs.
        # Force a full reprocess so variants with existing protein_sequence are
        # not skipped when mutation rows need to be regenerated.
        run_sequence_processing(exp_id_int, force_reprocess=True)
        message = 'Sequence processing completed. Mutation outputs were refreshed in the database.'
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
