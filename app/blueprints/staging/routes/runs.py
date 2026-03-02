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
    get_sequence_status_from_session,
    is_sequence_reprocess_required,
    save_sequence_status_to_session,
)

from .. import staging_bp


def _has_persisted_sequence_outputs(experiment_id: int) -> bool:
    """Return True when all variants for the experiment have sequence rows."""
    counts = _get_sequence_progress_counts(experiment_id)
    total_variants = counts[0]
    analysed_variants = counts[1]
    return total_variants > 0 and analysed_variants >= total_variants


def _get_sequence_progress_counts(experiment_id: int) -> tuple[int, int]:
    """Return total and analysed variant counts for one experiment."""
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
        return total_variants, analysed_variants
    except Exception:
        db.session.rollback()
        return 0, 0


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


def _sequence_run_state(experiment_id: int) -> tuple[str, str]:
    """Summarize the current sequence-processing state for polling clients."""
    session_state = get_sequence_status_from_session(experiment_id) or {}
    session_code = str(session_state.get('status', '')).lower()
    session_summary = str(session_state.get('summary') or '').strip()

    try:
        from app.services.sequence.db_repo import get_engine, get_experiment_status

        engine = get_engine()
        db_status = str(get_experiment_status(engine, experiment_id) or '').upper()
    except Exception:
        db.session.rollback()
        db_status = ''

    if session_code == 'failed' or db_status == 'FAILED':
        return 'failed', session_summary or 'Sequence processing failed.'

    if not is_sequence_reprocess_required(experiment_id) and _has_persisted_sequence_outputs(experiment_id):
        message = session_summary or 'Sequence processing completed. Mutation outputs were refreshed.'
        return 'completed', message

    if db_status == 'ANALYSIS_RUNNING':
        return 'running', 'Sequence processing is still running.'

    if session_code == 'running':
        return 'running', session_summary or 'Sequence processing is still running.'

    return 'idle', session_summary or 'Sequence processing has not started yet.'


@staging_bp.post('/analysis/run')
@login_required
def run_analysis():
    """Run analysis only when sequence outputs already exist."""
    experiment_id = request.form.get('experiment_id', '').strip()
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not experiment_id.isdigit():
        if is_xhr:
            return jsonify({'state': 'failed', 'message': 'Missing experiment_id.'}), 400
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    if not _has_sequence_outputs(exp_id_int):
        message = 'Run sequence processing first. Analysis only generates plots and reports from existing sequence outputs.'
        redirect_url = url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            analysis_message=message,
        )
        if is_xhr:
            return jsonify({'state': 'failed', 'message': message, 'redirect_url': redirect_url}), 409
        return redirect(redirect_url)

    ok, analysis_message = run_analysis_for_experiment(exp_id_int, current_app._get_current_object())
    if not ok and not analysis_message:
        analysis_message = 'Analysis failed.'

    redirect_url = url_for(
        'staging.create_experiment',
        experiment_id=experiment_id,
        analysis_message=analysis_message,
    )
    if is_xhr:
        return jsonify(
            {
                'state': 'completed' if ok else 'failed',
                'message': analysis_message,
                'redirect_url': redirect_url,
            }
        ), (200 if ok else 500)

    return redirect(redirect_url)


@staging_bp.post('/sequence/run')
@login_required
def run_sequence():
    """Run sequence processing; use background mode for XHR clients."""
    experiment_id = request.form.get('experiment_id', '').strip()
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    if not experiment_id.isdigit():
        if is_xhr:
            return jsonify({'state': 'failed', 'message': 'Missing experiment_id.'}), 400
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    # Step 4 is the explicit mutation-recompute step. Always run the full
    # sequence pipeline so mutation outputs are refreshed deterministically.
    force_reprocess = True
    redirect_url = url_for(
        'staging.create_experiment',
        experiment_id=experiment_id,
        sequence_message='Sequence processing is running.',
    )

    if is_xhr:
        state, message = _sequence_run_state(exp_id_int)
        if state == 'running':
            return jsonify({'state': state, 'message': message, 'redirect_url': redirect_url}), 202
        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            save_sequence_status_to_session(
                exp_id_int,
                {
                    'status': 'running',
                    'summary': 'Sequence processing is running.',
                    'technical_details': '',
                    'started_at_epoch': int(time.time()),
                },
            )
            submit_sequence_processing(exp_id_int, force_reprocess=force_reprocess)
            return jsonify(
                {
                    'state': 'started',
                    'message': 'Sequence processing started.',
                    'redirect_url': redirect_url,
                }
            ), 202
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
            return jsonify(
                {
                    'state': 'failed',
                    'message': message,
                    'redirect_url': url_for(
                        'staging.create_experiment',
                        experiment_id=experiment_id,
                        sequence_message=message,
                    ),
                }
            ), 500

    ok, message = _run_sequence_processing_for_experiment(
        exp_id_int,
        force_reprocess=force_reprocess,
    )

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))


@staging_bp.get('/sequence/status')
@login_required
def sequence_status():
    """Return the current Step 4 state for async clients."""
    experiment_id = request.args.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return jsonify({'state': 'failed', 'message': 'Missing experiment_id.'}), 400

    exp_id_int = int(experiment_id)
    state, message = _sequence_run_state(exp_id_int)
    total_variants, analysed_variants = _get_sequence_progress_counts(exp_id_int)
    percent_complete = 0
    if total_variants > 0:
        percent_complete = int(min(100, max(0, round((analysed_variants / total_variants) * 100))))
    if state == 'completed':
        percent_complete = 100
    return jsonify(
        {
            'state': state,
            'message': message,
            'total_variants': total_variants,
            'analysed_variants': analysed_variants,
            'percent_complete': percent_complete,
            'redirect_url': url_for(
                'staging.create_experiment',
                experiment_id=experiment_id,
                sequence_message=message,
            ),
        }
    )
