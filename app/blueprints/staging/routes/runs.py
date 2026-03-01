"""Analysis and sequence execution endpoints for staging."""

import time
import traceback

from flask import current_app, redirect, request, url_for
from flask_login import login_required
from sqlalchemy import text

from app.extensions import db
from app.services.staging.analysis_runtime import run_analysis_for_experiment
from app.services.staging.session_state import (
    clear_sequence_reprocess_required,
    is_sequence_reprocess_required,
    save_sequence_status_to_session,
)

from .. import staging_bp


def _run_sequence_processing_for_experiment(
    experiment_id: int,
    *,
    force_reprocess: bool,
) -> tuple[bool, str]:
    """Run sequence processing synchronously and persist UI status text."""
    try:
        from app.jobs.run_sequence_processing import run_sequence_processing

        run_sequence_processing(experiment_id, force_reprocess=force_reprocess)
        clear_sequence_reprocess_required(experiment_id)
        if force_reprocess:
            message = (
                'Sequence processing completed. Full mutation outputs were refreshed '
                'because the experiment inputs changed.'
            )
        else:
            message = (
                'Sequence processing completed. Existing valid outputs were reused; '
                'only missing variants were processed.'
            )
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
    if is_sequence_reprocess_required(experiment_id):
        return False

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
    force_reprocess = request.form.get('force_reprocess', '').strip().lower() in {'1', 'true', 'yes', 'on'}
    if not force_reprocess:
        force_reprocess = is_sequence_reprocess_required(exp_id_int)
    _, message = _run_sequence_processing_for_experiment(
        exp_id_int,
        force_reprocess=force_reprocess,
    )

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))
