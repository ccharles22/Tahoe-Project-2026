"""Embedded analysis routes used by the UI_test Flask application."""

from __future__ import annotations

from pathlib import Path
import time
from flask import Flask, render_template, request
import numpy as np
import pandas as pd

try:
    from scipy.stats import linregress
except ImportError:  # pragma: no cover - runtime fallback for lean installs.
    linregress = None

from .database import get_conn
from .queries import (
    fetch_top10, fetch_distribution,
    fetch_lineage_nodes, fetch_lineage_edges,
    fetch_variant_raw, fetch_wt_baselines,
    fetch_protein_similarity_nodes, fetch_protein_mutations, fetch_network_diagnostics,
)

from .plots.top10 import plot_top10_table
from .plots.distribution import plot_activity_distribution
from .plots.lineage import plot_layered_lineage, plot_relative_expression_trend
from .plots.protein_similarity_network import (
    ProteinNetConfig,
    plot_protein_similarity_network,
)

import logging

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_DIR = ROOT_DIR / "app"


def _format_pvalue_label(pvalue: float | None) -> str:
    """Return a human-readable trend p-value label."""
    if pvalue is None or not np.isfinite(pvalue):
        return "Trend p-value: unavailable"
    if pvalue < 0.001:
        return "Trend p-value: < 0.001"
    return f"Trend p-value: {pvalue:.3f}"


def _build_expression_trend(conn, experiment_id: int) -> tuple[pd.DataFrame, str, float | None]:
    """Compute per-generation relative protein expression and a trend p-value."""
    raw = fetch_variant_raw(conn, experiment_id)
    if raw.empty:
        return pd.DataFrame(), "No expression baseline available", None

    baselines, missing_generations = fetch_wt_baselines(conn, experiment_id)
    baseline_lookup = {gid: values[1] for gid, values in baselines.items()}

    df = raw.copy()
    df["generation_id"] = pd.to_numeric(df["generation_id"], errors="coerce")
    df["generation_number"] = pd.to_numeric(df["generation_number"], errors="coerce")
    df["protein_yield_raw"] = pd.to_numeric(df["protein_yield_raw"], errors="coerce")
    df = df.dropna(subset=["generation_id", "generation_number", "protein_yield_raw"])

    if df.empty:
        return pd.DataFrame(), "No expression baseline available", None

    df["generation_id"] = df["generation_id"].astype(int)
    df["generation_number"] = df["generation_number"].astype(int)
    df["generation_median_protein"] = (
        df.groupby("generation_id")["protein_yield_raw"].transform("median")
    )
    df["expression_baseline"] = df["generation_id"].map(baseline_lookup)

    missing_baseline = (
        df["expression_baseline"].isna() | (pd.to_numeric(df["expression_baseline"], errors="coerce") <= 0)
    )
    df.loc[missing_baseline, "expression_baseline"] = df.loc[missing_baseline, "generation_median_protein"]

    df["expression_baseline"] = pd.to_numeric(df["expression_baseline"], errors="coerce")
    df = df[df["expression_baseline"] > 0].copy()

    if df.empty:
        label = "Relative to generation median"
        return pd.DataFrame(), label, None

    df["relative_expression"] = df["protein_yield_raw"] / df["expression_baseline"]

    trend = (
        df.groupby("generation_number", as_index=False)["relative_expression"]
        .agg(
            mean_relative_expression="mean",
            min_relative_expression="min",
            max_relative_expression="max",
        )
        .sort_values("generation_number")
    )

    pvalue: float | None = None
    if (
        linregress is not None
        and len(trend) >= 2
        and trend["mean_relative_expression"].nunique() > 1
    ):
        result = linregress(
            trend["generation_number"].to_numpy(dtype=float),
            trend["mean_relative_expression"].to_numpy(dtype=float),
        )
        pvalue = float(result.pvalue)

    if missing_generations:
        label = "Relative to WT baseline when available; otherwise generation median"
    else:
        label = "Relative to WT baseline"

    return trend, label, pvalue

def register_analysis_routes(target_app: Flask) -> None:
    """Attach the analysis views to an existing Flask app instance."""
    plots_dir = Path(target_app.static_folder) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    @target_app.route("/top10/<int:experiment_id>")
    def top10(experiment_id: int):
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
        with get_conn() as conn:
            nodes = fetch_lineage_nodes(conn, experiment_id)
            edges = fetch_lineage_edges(conn, experiment_id)
            expression_trend, expression_baseline_label, expression_pvalue = _build_expression_trend(
                conn,
                experiment_id,
            )

        out_path = plots_dir / f"lineage_exp{experiment_id}.png"
        expr_out_path = plots_dir / f"lineage_expr_exp{experiment_id}.png"
        plot_layered_lineage(nodes, edges, out_path)
        plot_relative_expression_trend(expression_trend, expr_out_path)

        return render_template(
            "analysis/lineage.html",
            experiment_id=experiment_id,
            lineage_png=f"plots/lineage_exp{experiment_id}.png",
            expression_png=f"plots/lineage_expr_exp{experiment_id}.png",
            expression_baseline_label=expression_baseline_label,
            expression_pvalue_label=_format_pvalue_label(expression_pvalue),
        )

    @target_app.route("/protein_similarity/<int:experiment_id>")
    def protein_similarity(experiment_id: int):
        requested_mode_raw = (request.args.get("mode") or "").strip().lower()
        if requested_mode_raw in {"identity", "cooccurrence"}:
            mode = requested_mode_raw
        else:
            if requested_mode_raw:
                logger.warning(
                    "Invalid protein network mode '%s' for experiment %s; defaulting to identity.",
                    requested_mode_raw,
                    experiment_id,
                )
            else:
                logger.info(
                    "No protein network mode provided for experiment %s; defaulting to identity.",
                    experiment_id,
                )
            mode = "identity"

        preset = request.args.get("preset", "").strip().lower()
        identity_threshold = request.args.get("identity_threshold", "0.95")
        min_shared = request.args.get("min_shared", "1")
        jaccard_threshold = request.args.get("jaccard_threshold", "")
        max_nodes = request.args.get("max_nodes", "40")

        allowed_max_nodes = {20, 30, 40, 50, 80, 120, 250}

        try:
            identity_threshold_val = float(identity_threshold)
        except ValueError:
            identity_threshold_val = 0.95

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

        try:
            max_nodes_val = int(max_nodes)
        except ValueError:
            max_nodes_val = 40
        if max_nodes_val not in allowed_max_nodes:
            max_nodes_val = 40

        if preset in {"sparse", "medium", "dense"}:
            if mode == "identity":
                identity_threshold_val = {"sparse": 0.98, "medium": 0.95, "dense": 0.90}[preset]
            else:
                preset_map = {
                    "sparse": (4, 0.20),
                    "medium": (2, 0.10),
                    "dense": (1, None),
                }
                min_shared_val, jaccard_threshold_val = preset_map[preset]

        with get_conn() as conn:
            nodes = fetch_protein_similarity_nodes(conn, experiment_id)
            mutations = fetch_protein_mutations(conn, experiment_id) if mode == "cooccurrence" else None
            diagnostics = fetch_network_diagnostics(conn, experiment_id)

        mutations_loaded = diagnostics.get("mutation_rows_total", 0)
        proteins_available = diagnostics.get("protein_sequences_available", 0)
        network_data_warning = ""
        if mode == "cooccurrence" and mutations_loaded < 50:
            network_data_warning = (
                "Co-occurrence network may be sparse because few mutation rows were persisted."
            )

        suffix = f"{mode}_it{identity_threshold_val:.2f}_ms{min_shared_val}_n{max_nodes_val}"
        if jaccard_threshold_val is not None:
            suffix = f"{suffix}_jt{jaccard_threshold_val:.2f}"
        out_path = plots_dir / f"protein_exp{experiment_id}_{suffix}.png"

        if mode == "identity":
            title = f"Protein Similarity Network (Top {max_nodes_val} Variants by Activity)"
        else:
            title = f"Protein Co-Occurrence Network (Top {max_nodes_val} Variants by Activity)"
        config = ProteinNetConfig(
            title=title,
            identity_threshold=identity_threshold_val,
            cooccur_min_shared_mutations=min_shared_val,
            cooccur_jaccard_threshold=jaccard_threshold_val,
            top_n_by_activity=max_nodes_val,
            max_nodes_final=max_nodes_val,
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
            mode_label=("Sequence identity" if mode == "identity" else "Mutation co-occurrence"),
            preset=preset,
            identity_threshold=identity_threshold_val,
            min_shared=min_shared_val,
            jaccard_threshold=jaccard_threshold_val if jaccard_threshold_val is not None else "",
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


app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)

register_analysis_routes(app)
