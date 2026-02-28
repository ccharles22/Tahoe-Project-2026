"""Background analysis runtime helpers for staging workflows."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from flask import current_app

logger = logging.getLogger(__name__)

_BONUS_VIEW_NAMES = (
    'mv_activity_landscape',
    'mv_domain_mutation_enrichment',
)


def generate_protein_network_plot(experiment_id: int) -> tuple[bool, str]:
    """Generate protein similarity network PNG for one experiment."""
    try:
        from app.services.analysis.database import get_conn
        from app.services.analysis.plots.protein_similarity_network import plot_protein_similarity_network
        from app.services.analysis.queries import fetch_protein_similarity_nodes
    except Exception as exc:
        return False, f'Protein network setup failed: {exc}'

    out_dir = os.path.join(current_app.root_path, 'static', 'generated', str(experiment_id))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'protein_similarity.png')

    try:
        with get_conn() as conn:
            df_protein = fetch_protein_similarity_nodes(conn, experiment_id)
        if df_protein.empty:
            return False, 'Protein network skipped: no variants available.'
        if df_protein['protein_sequence'].dropna().empty:
            return False, 'Protein network skipped: no protein sequences available.'

        plot_protein_similarity_network(
            df_protein,
            out_path,
            id_col='variant_id',
            seq_col='protein_sequence',
            activity_col='activity_score',
            top_col='is_top10',
        )
        return True, 'Protein network generated.'
    except Exception as exc:
        return False, f'Protein network failed: {exc}'


def _get_latest_generation_id(experiment_id: int) -> int | None:
    """Return latest generation_id for an experiment, or None when unavailable."""
    try:
        from app.services.analysis.database import get_conn
    except Exception:
        return None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT g.generation_id
                    FROM generations g
                    WHERE g.experiment_id = %s
                    ORDER BY g.generation_number DESC, g.generation_id DESC
                    LIMIT 1
                    """,
                    (experiment_id,),
                )
                row = cur.fetchone()
        if not row:
            return None
        return int(row[0])
    except Exception:
        return None


def _missing_bonus_views() -> list[str] | None:
    """Return missing bonus materialized views, or None when the check cannot run."""
    try:
        from app.services.analysis.database import get_conn
    except Exception:
        return None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT matviewname
                    FROM pg_matviews
                    WHERE schemaname = current_schema()
                      AND matviewname = ANY(%s)
                    """,
                    (list(_BONUS_VIEW_NAMES),),
                )
                existing = {str(row[0]) for row in cur.fetchall()}
    except Exception:
        return None

    return [name for name in _BONUS_VIEW_NAMES if name not in existing]


def run_bonus_analysis_for_experiment(experiment_id: int, app_obj) -> tuple[bool, str]:
    """Run bonus analysis pipeline for the latest generation in this experiment."""
    generation_id = _get_latest_generation_id(experiment_id)
    if generation_id is None:
        return False, 'Bonus outputs skipped: no generation found.'

    repo_root = os.path.dirname(app_obj.root_path)
    missing_views = _missing_bonus_views()
    if missing_views:
        missing_csv = ', '.join(missing_views)
        return (
            False,
            'Bonus outputs skipped: required bonus materialized views are missing '
            f'({missing_csv}). Create them once, then rerun analysis.',
        )
    out_dir = os.path.join(app_obj.root_path, 'static', 'generated', str(experiment_id), 'bonus')
    os.makedirs(out_dir, exist_ok=True)

    proc = subprocess.run(
        [
            sys.executable,
            '-m',
            'app.services.analysis.bonus.pipelines.run_bonus_pipeline',
            '--generation-id',
            str(generation_id),
            '--outputs-dir',
            out_dir,
            '--landscape-method',
            'pca',
            '--landscape-mode',
            'surface',
            '--top-n',
            '10',
            '--skip-create-views',
        ],
        cwd=repo_root,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        details = proc.stderr[-1200:] if proc.stderr else (proc.stdout[-1200:] if proc.stdout else 'no output')
        logger.warning(
            'Bonus analysis failed for experiment %s generation %s (code=%s): %s',
            experiment_id,
            generation_id,
            proc.returncode,
            details,
        )
        return False, f'Bonus outputs failed to generate: {details}'

    return True, 'Bonus outputs generated.'


def run_analysis_for_experiment(experiment_id: int, app_obj) -> tuple[bool, str]:
    """Run analysis for one experiment and return success state + message."""
    repo_root = os.path.dirname(app_obj.root_path)
    env = os.environ.copy()
    env['EXPERIMENT_ID'] = str(experiment_id)
    try:
        proc = subprocess.run(
            [sys.executable, '-m', 'app.services.analysis.report'],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            details = proc.stderr[-2000:] if proc.stderr else 'no stderr'
            logger.error(
                'Analysis failed for experiment %s (code=%s): %s',
                experiment_id,
                proc.returncode,
                details,
            )
            return False, f'Analysis failed (code {proc.returncode}).'

        with app_obj.app_context():
            generated, protein_msg = generate_protein_network_plot(experiment_id)
            bonus_generated, bonus_msg = run_bonus_analysis_for_experiment(experiment_id, app_obj)
            if generated:
                logger.info('Analysis complete for experiment %s.', experiment_id)
                if bonus_generated:
                    return True, 'Analysis complete. Outputs refreshed, including bonus visuals.'
                return True, f'Analysis complete. Outputs refreshed. {bonus_msg}'
            logger.info('Analysis complete for experiment %s with note: %s', experiment_id, protein_msg)
            if bonus_generated:
                return True, f'Analysis complete. {protein_msg} Bonus visuals generated.'
            return True, f'Analysis complete. {protein_msg} {bonus_msg}'
    except Exception:
        logger.exception('Analysis crashed for experiment %s', experiment_id)
        return False, 'Analysis failed due to an unexpected server error.'


def run_analysis_background(experiment_id: int, app_obj) -> None:
    """Run analysis in a background thread to avoid blocking web requests."""
    run_analysis_for_experiment(experiment_id, app_obj)
