"""Embedded analysis routes used by the UI_test Flask application."""

from __future__ import annotations

from pathlib import Path
import time
from flask import Flask, render_template, request
import numpy as np
import pandas as pd

from .database import get_conn
from .queries import (
    fetch_top10, fetch_distribution,
    fetch_lineage_nodes, fetch_lineage_edges,
    fetch_protein_similarity_nodes, fetch_protein_mutations, fetch_network_diagnostics,
)

from .plots.top10 import plot_top10_table
from .plots.distribution import plot_activity_distribution
from .plots.lineage import (
    PlotConfig,
    compute_top_variants_branch_trend,
    plot_layered_lineage,
)
from .plots.protein_similarity_network import (
    ProteinNetConfig,
    plot_protein_similarity_network,
)

import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_DIR = ROOT_DIR / "app"


def _format_pvalue_label(pvalue: float | None) -> str:
    """Return p-value label without threshold buckets (show numeric value directly)."""
    if pvalue is None or not np.isfinite(pvalue):
        return "Trend p-value: unavailable"
    return f"Trend p-value: {pvalue:.16g}"


def _format_pearson_label(rvalue: float | None) -> str:
    """Return a human-readable Pearson correlation label."""
    if rvalue is None or not np.isfinite(rvalue):
        return "Pearson r: unavailable"
    return f"Pearson r: {rvalue:.3f}"

def register_analysis_routes(target_app: Flask) -> None:
    """Attach the analysis views to an existing Flask app instance.

    Registers four routes: ``/top10``, ``/distribution``, ``/lineage``, and
    ``/protein_similarity``, each parameterised by ``experiment_id``.  Plot
    images are written into the app's static directory under ``plots/``.
    """
    plots_dir = Path(target_app.static_folder) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    @target_app.route("/top10/<int:experiment_id>")
    def top10(experiment_id: int):
        """Render the top-10 variants table page for a given experiment."""
        with get_conn() as conn:
            df = fetch_top10(conn, experiment_id)

        out_path = plots_dir / f"top10_exp{experiment_id}.png"
        plot_top10_table(df, out_path)

        top10_rows = []
        max_score = 0.0
        if not df.empty:
            for idx, row in enumerate(df.itertuples(index=False), start=1):
                score = float(row.activity_score)
                max_score = max(max_score, score)
                top10_rows.append(
                    {
                        "rank": idx,
                        "variant_id": int(row.variant_id),
                        "generation_number": int(row.generation_number),
                        "plasmid_variant_index": str(row.plasmid_variant_index),
                        "activity_score": score,
                        "total_mutations": (
                            None if pd.isna(row.total_mutations) else int(row.total_mutations)
                        ),
                    }
                )

        return render_template(
            "analysis/top10.html",
            experiment_id=experiment_id,
            top10_png=f"plots/top10_exp{experiment_id}.png",
            top10_rows=top10_rows,
            top10_max_score=max_score,
        )

    @target_app.route("/distribution/<int:experiment_id>")
    def distribution(experiment_id: int):
        """Render the activity-score distribution plot page."""
        with get_conn() as conn:
            df = fetch_distribution(conn, experiment_id)

        out_path = plots_dir / f"dist_exp{experiment_id}.png"
        plot_activity_distribution(df, out_path)

        return render_template(
            "analysis/distribution.html",
            experiment_id=experiment_id,
            dist_png=f"plots/dist_exp{experiment_id}.png",
        )

    @target_app.route("/lineage/<int:experiment_id>")
    def lineage(experiment_id: int):
        """Render the lineage DAG page, optionally overlaying a branch trend."""
        show_trend = request.args.get("show_trend", "").strip().lower() in {"1", "true", "yes", "on"}
        with get_conn() as conn:
            nodes = fetch_lineage_nodes(conn, experiment_id)
            edges = fetch_lineage_edges(conn, experiment_id)

        trend_stats = compute_top_variants_branch_trend(
            nodes,
            edges,
            top_n=10,
            min_points=3,
        )

        variant_count = len(trend_stats.top_variant_ids)
        trend_scope_label = (
            f"Top-{variant_count} branch trend" if variant_count > 0 else "Top-variants branch trend"
        )

        suffix = "trend" if show_trend else "plain"
        out_path = plots_dir / f"lineage_exp{experiment_id}_{suffix}.png"
        plot_layered_lineage(
            nodes,
            edges,
            out_path,
            config=PlotConfig(show_top10_branch_trend=show_trend),
        )

        return render_template(
            "analysis/lineage.html",
            experiment_id=experiment_id,
            lineage_png=f"plots/lineage_exp{experiment_id}_{suffix}.png",
            show_trend=show_trend,
            trend_scope_label=trend_scope_label,
            trend_point_count=trend_stats.point_count,
            trend_ready=trend_stats.trend_ready,
            trend_pvalue_label=_format_pvalue_label(trend_stats.p_value),
            trend_pearson_label=_format_pearson_label(trend_stats.r_value),
            cache_bust=int(time.time()),
        )

    @target_app.route("/protein_similarity/<int:experiment_id>")
    def protein_similarity(experiment_id: int):
        """Render the protein co-occurrence network page with tuneable filters."""
        preset = request.args.get("preset", "").strip().lower()
        min_shared = request.args.get("min_shared", "1")
        jaccard_threshold = request.args.get("jaccard_threshold", "")
        pearson_threshold = request.args.get("pearson_threshold", "0.20")
        max_nodes = request.args.get("max_nodes", "20")

        allowed_max_nodes = {20, 30, 40, 50, 80, 120, 250}

        try:
            min_shared_val = max(1, int(min_shared))
        except ValueError:
            min_shared_val = 1

        jaccard_threshold_val = None
        if jaccard_threshold.strip():
            try:
                jaccard_threshold_val = float(jaccard_threshold)
            except ValueError:
                jaccard_threshold_val = None

        pearson_threshold_val = None
        if pearson_threshold.strip():
            try:
                pearson_threshold_val = float(np.clip(float(pearson_threshold), -1.0, 1.0))
            except ValueError:
                pearson_threshold_val = 0.20

        try:
            max_nodes_val = int(max_nodes)
        except ValueError:
            max_nodes_val = 20
        if max_nodes_val not in allowed_max_nodes:
            max_nodes_val = 20

        # Named presets override manually entered filter values.
        if preset in {"sparse", "medium", "dense"}:
            preset_map = {
                "sparse": (4, 0.20),
                "medium": (2, 0.10),
                "dense": (1, None),
            }
            min_shared_val, jaccard_threshold_val = preset_map[preset]

        with get_conn() as conn:
            nodes = fetch_protein_similarity_nodes(conn, experiment_id)
            mutations = fetch_protein_mutations(conn, experiment_id)
            diagnostics = fetch_network_diagnostics(conn, experiment_id)

        mutations_loaded = diagnostics.get("mutation_rows_total", 0)
        proteins_available = diagnostics.get("protein_sequences_available", 0)
        network_data_warning = ""
        if mutations_loaded < 50:
            network_data_warning = (
                "Co-occurrence network may be sparse because few mutation rows were persisted."
            )

        # Build a unique filename suffix from filter parameters to avoid cache collisions.
        mode = "cooccurrence"
        suffix = f"{mode}_n{max_nodes_val}_ms{min_shared_val}"
        if jaccard_threshold_val is not None:
            suffix = f"{suffix}_jt{jaccard_threshold_val:.2f}"
        if pearson_threshold_val is not None:
            suffix = f"{suffix}_pt{pearson_threshold_val:.2f}"
        out_path = plots_dir / f"protein_exp{experiment_id}_{suffix}.png"

        title = f"Protein Co-Occurrence Network (Top {max_nodes_val} Variants by Activity)"
        mode_label = "Mutation co-occurrence (Jaccard + Pearson filters)"
        config = ProteinNetConfig(
            title=title,
            cooccur_min_shared_mutations=min_shared_val,
            cooccur_jaccard_threshold=jaccard_threshold_val,
            cooccur_pearson_threshold=pearson_threshold_val,
            top_n_by_activity=max_nodes_val,
            max_nodes_final=max_nodes_val,
            mode=mode,
        )

        plot_protein_similarity_network(
            nodes,
            out_path,
            mode=mode,
            mutations=mutations,
            config=config,
        )

        return render_template(
            "analysis/protein_similarity.html",
            experiment_id=experiment_id,
            protein_png=f"plots/protein_exp{experiment_id}_{suffix}.png",
            mode=mode,
            mode_label=mode_label,
            preset=preset,
            min_shared=min_shared_val,
            jaccard_threshold=jaccard_threshold_val if jaccard_threshold_val is not None else "",
            pearson_threshold=pearson_threshold_val if pearson_threshold_val is not None else "",
            max_nodes=max_nodes_val,
            max_node_options=sorted(allowed_max_nodes),
            mutations_loaded=mutations_loaded,
            proteins_available=proteins_available,
            mutation_rows_protein=diagnostics.get("mutation_rows_protein", 0),
            mutation_rows_dna=diagnostics.get("mutation_rows_dna", 0),
            mutation_rows_json=diagnostics.get("json_mutation_rows", 0),
            network_data_warning=network_data_warning,
            cache_buster=int(time.time()),
        )


# Module-level Flask app instance used when this file is run directly or
# imported as the WSGI entry point for the analysis sub-application.
app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)

register_analysis_routes(app)
