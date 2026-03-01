"""Analysis and sequence execution endpoints for staging."""

import time
import traceback

from flask import current_app, jsonify, redirect, request, url_for
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
    """Run sequence processing and return only when it finishes."""
    experiment_id = request.form.get('experiment_id', '').strip()
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not experiment_id.isdigit():
        if is_xhr:
            return jsonify({'state': 'failed', 'message': 'Missing experiment_id.'}), 400
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    # Step 4 is the explicit "recompute sequence outputs" action, so it should
    # always run the full sequence pipeline rather than silently skipping
    # already-processed variants.
    force_reprocess = True
    ok, message = _run_sequence_processing_for_experiment(
        exp_id_int,
        force_reprocess=force_reprocess,
    )
    if is_xhr:
        return jsonify({'state': 'completed' if ok else 'failed', 'message': message}), (200 if ok else 500)

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))
