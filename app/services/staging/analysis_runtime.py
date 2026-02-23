"""Background analysis runtime helpers for staging workflows."""

from __future__ import annotations

import logging
import os
import subprocess
import sys

from flask import current_app

logger = logging.getLogger(__name__)


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


def run_analysis_background(experiment_id: int, app_obj) -> None:
    """Run analysis in a background thread to avoid blocking web requests."""
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
            logger.error(
                'Background analysis failed for experiment %s (code=%s): %s',
                experiment_id,
                proc.returncode,
                proc.stderr[-2000:] if proc.stderr else 'no stderr',
            )
            return

        with app_obj.app_context():
            generated, protein_msg = generate_protein_network_plot(experiment_id)
            logger.info(
                'Background analysis complete for experiment %s: %s',
                experiment_id,
                'Protein network generated.' if generated else protein_msg,
            )
    except Exception:
        logger.exception('Background analysis crashed for experiment %s', experiment_id)
