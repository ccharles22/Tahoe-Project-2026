"""Analysis report generation used by the staging workflow and scripts."""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from .database import get_conn
from .queries import (
    fetch_wt_baselines,
    fetch_variant_raw,
    fetch_top10,
    fetch_distribution,
    fetch_lineage_nodes,
    fetch_lineage_edges,
)
from .activity_score import compute_stage4_metrics
from .metrics import upsert_variant_metrics

# New matplotlib-based plots (from teammate's MPL branch)
from .plots.distribution import plot_activity_distribution
from .plots.top10 import plot_top10_table
from .plots.lineage import plot_layered_lineage, PlotConfig

OUTPUT_DIR = "app/static/generated"


# ── WT-free fallback scoring ────────────────────────────────────
def compute_activity_score_fallback(
    df_variants: pd.DataFrame,
) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    WT-free scoring fallback:
    - Within each generation, normalise DNA and protein yields by generation median
    - activity_score = dna_norm / protein_norm
    """
    d = df_variants.copy()

    required = {"variant_id", "generation_id", "dna_yield_raw", "protein_yield_raw"}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f"Fallback scoring requires columns {sorted(required)}; missing {sorted(missing)}")

    d["dna_yield_raw"] = pd.to_numeric(d["dna_yield_raw"], errors="coerce")
    d["protein_yield_raw"] = pd.to_numeric(d["protein_yield_raw"], errors="coerce")

    d["dna_med"] = d.groupby("generation_id")["dna_yield_raw"].transform("median")
    d["prot_med"] = d.groupby("generation_id")["protein_yield_raw"].transform("median")

    d.loc[d["dna_med"] == 0, "dna_med"] = np.nan
    d.loc[d["prot_med"] == 0, "prot_med"] = np.nan

    d["dna_yield_norm"] = d["dna_yield_raw"] / d["dna_med"]
    d["protein_yield_norm"] = d["protein_yield_raw"] / d["prot_med"]
    d["activity_score"] = d["dna_yield_norm"] / d["protein_yield_norm"]

    d["qc_stage4"] = "ok"
    bad_mask = (
        d["variant_id"].isna()
        | d["generation_id"].isna()
        | d["dna_yield_norm"].isna()
        | d["protein_yield_norm"].isna()
        | d["activity_score"].isna()
        | ~np.isfinite(d["activity_score"].to_numpy())
        | ~np.isfinite(d["dna_yield_norm"].to_numpy())
        | ~np.isfinite(d["protein_yield_norm"].to_numpy())
    )
    d.loc[bad_mask, "qc_stage4"] = "invalid_fallback"

    ok = d[d["qc_stage4"] == "ok"].copy()

    rows: List[Dict[str, Any]] = []
    for r in ok.itertuples(index=False):
        vid = int(r.variant_id)
        gid = int(r.generation_id)
        rows.extend([
            {"generation_id": gid, "variant_id": vid, "metric_name": "dna_yield_norm",
             "metric_type": "normalized", "value": float(r.dna_yield_norm), "unit": "ratio"},
            {"generation_id": gid, "variant_id": vid, "metric_name": "protein_yield_norm",
             "metric_type": "normalized", "value": float(r.protein_yield_norm), "unit": "ratio"},
            {"generation_id": gid, "variant_id": vid, "metric_name": "activity_score",
             "metric_type": "derived", "value": float(r.activity_score), "unit": "ratio"},
        ])

    return rows, d


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_plasmid_index(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        as_num = float(text)
        if as_num.is_integer():
            return str(int(as_num))
    except (TypeError, ValueError):
        pass
    return text


def _build_placeholder_edges(
    df_nodes: pd.DataFrame,
    *,
    node_id_col: str,
    generation_col: str,
    index_col: str,
    max_distance: float,
) -> pd.DataFrame:
    """
    Create synthetic parent edges when parent_variant_id is missing.
    Strategy: nearest numeric index in previous generation within max_distance.
    """
    required = {node_id_col, generation_col, index_col}
    if not required.issubset(df_nodes.columns):
        return pd.DataFrame(columns=["parent_id", "child_id"])

    d = df_nodes[[node_id_col, generation_col, index_col]].copy()
    d[generation_col] = pd.to_numeric(d[generation_col], errors="coerce")
    d = d.dropna(subset=[node_id_col, generation_col])
    if d.empty:
        return pd.DataFrame(columns=["parent_id", "child_id"])

    d["_idx_str"] = d[index_col].map(_normalize_plasmid_index)
    d["_idx_num"] = pd.to_numeric(d["_idx_str"], errors="coerce")

    groups = {int(g): sub.copy() for g, sub in d.groupby(generation_col)}
    if not groups:
        return pd.DataFrame(columns=["parent_id", "child_id"])

    min_gen = min(groups.keys())
    edges: list[tuple[int, int]] = []

    for gen, sub in groups.items():
        if gen <= min_gen:
            continue
        prev = groups.get(gen - 1)
        if prev is None or prev.empty:
            continue

        prev_num = prev.dropna(subset=["_idx_num"])[["_idx_num", node_id_col]].to_numpy()

        for _, row in sub.iterrows():
            child_id = row[node_id_col]
            idx_num = row["_idx_num"]

            parent_id = None
            if pd.notna(idx_num) and len(prev_num) > 0:
                diffs = np.abs(prev_num[:, 0].astype(float) - float(idx_num))
                min_idx = int(diffs.argmin())
                if float(diffs[min_idx]) <= max_distance:
                    parent_id = int(prev_num[min_idx, 1])

            if parent_id is not None:
                edges.append((int(parent_id), int(child_id)))

    return pd.DataFrame(edges, columns=["parent_id", "child_id"])


def main():
    """Run the reporting pipeline for the experiment in ``EXPERIMENT_ID``."""
    exp_env = os.getenv("EXPERIMENT_ID")
    if exp_env is None or not str(exp_env).strip():
        raise RuntimeError(
            "EXPERIMENT_ID is required. "
            "Set it explicitly before running analysis "
            "(for example: $env:EXPERIMENT_ID='74')."
        )
    try:
        experiment_id = int(str(exp_env).strip())
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid EXPERIMENT_ID '{exp_env}'. It must be an integer."
        ) from exc
    if experiment_id <= 0:
        raise RuntimeError(
            f"Invalid EXPERIMENT_ID '{experiment_id}'. It must be a positive integer."
        )
    exp_output_dir = os.path.join(OUTPUT_DIR, str(experiment_id))
    os.makedirs(exp_output_dir, exist_ok=True)
    require_wt_baseline = _env_bool("STAGE4_REQUIRE_WT_BASELINE", False)

    with get_conn() as conn:
        # 1) Raw variant metrics
        df_variants = fetch_variant_raw(conn, experiment_id)
        print(f"[Stage4] Variants fetched: {len(df_variants)}")
        if df_variants.empty:
            print("[Stage4] No variants for this experiment. Exiting.")
            return

        # 2) Prefer WT-based scoring and only fallback when no WT baselines exist.
        baselines, missing_generations = fetch_wt_baselines(conn, experiment_id)
        baseline_label = "WT control baseline = 1.0"

        if require_wt_baseline and missing_generations:
            raise RuntimeError(
                "STAGE4_REQUIRE_WT_BASELINE=true but WT baselines are missing for "
                f"generation(s): {missing_generations} (experiment {experiment_id})."
            )

        if baselines:
            score_mode = "WT-normalised"
            print(
                "[Stage4] Using WT scoring with baselines from "
                f"{len(baselines)} generation(s)."
            )
            if missing_generations:
                print(
                    "[Stage4] Missing WT baselines for generation(s) "
                    f"{missing_generations}; variants in those generations will be unscored "
                    "(qc_stage4=missing_wt_baseline) and excluded from scored plots."
                )
            rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)
        else:
            if require_wt_baseline:
                raise RuntimeError(
                    "STAGE4_REQUIRE_WT_BASELINE=true but no WT baselines were found "
                    f"for experiment {experiment_id}."
                )
            score_mode = "median-normalised fallback"
            baseline_label = "Generation median baseline = 1.0"
            print(
                "[Stage4] WT scoring unavailable: no valid WT baselines were found; "
                "using generation-median fallback scoring."
            )
            rows_to_insert, df_with_qc = compute_activity_score_fallback(df_variants)

        print(f"[Stage4] Scoring mode: {score_mode}")

        # 3) Upsert computed metrics
        inserted = upsert_variant_metrics(conn, rows_to_insert)
        print(f"[DB] Upserted {inserted} metric rows.")

        # 4) QC debug CSV
        qc_path = os.path.join(exp_output_dir, "stage4_qc_debug.csv")
        df_with_qc.to_csv(qc_path, index=False)
        print(f"[File] {qc_path}")

        # 5) Top-10 table (CSV + PNG)
        df_top10 = fetch_top10(conn, experiment_id)
        top10_csv = os.path.join(exp_output_dir, "top10_variants.csv")
        df_top10.to_csv(top10_csv, index=False)
        print(f"[File] {top10_csv} ({len(df_top10)} rows)")

        top10_png = os.path.join(exp_output_dir, "top10_variants.png")
        if not df_top10.empty:
            try:
                plot_top10_table(df_top10, top10_png)
                print(f"[File] {top10_png}")
            except Exception as e:
                print(f"[Plot] Top-10 table plot failed: {e}")

        # 6) Activity distribution violin plot
        df_dist = fetch_distribution(conn, experiment_id)
        dist_png = os.path.join(exp_output_dir, "activity_distribution.png")
        if not df_dist.empty:
            try:
                plot_activity_distribution(df_dist, dist_png, baseline_label=baseline_label)
                print(f"[File] {dist_png}")
            except Exception as e:
                print(f"[Plot] Distribution plot failed: {e}")
        else:
            print("[Plot] No distribution data; skipped.")

        # 7) Lineage graph
        df_nodes = fetch_lineage_nodes(conn, experiment_id)
        df_edges = fetch_lineage_edges(conn, experiment_id)
        lineage_png = os.path.join(exp_output_dir, "lineage.png")
        if not df_nodes.empty:
            try:
                if df_edges.empty:
                    df_edges = _build_placeholder_edges(
                        df_nodes,
                        node_id_col="variant_id",
                        generation_col="generation_number",
                        index_col="plasmid_variant_index",
                        max_distance=3.0,
                    )
                    print(f"[Lineage] Using placeholder edges: {len(df_edges)}")

                plot_layered_lineage(
                    df_nodes,
                    df_edges,
                    lineage_png,
                    config=PlotConfig(
                        label_mode="topk",
                        label_id_source="variant_id",
                        label_top_k_per_generation=1,
                        layout_mode="pack",
                        pack_generation_height=6.0,
                        label_fontsize=8,
                    ),
                )
                print(f"[File] {lineage_png}")
            except Exception as e:
                print(f"[Plot] Lineage plot failed: {e}")
        else:
            print("[Lineage] No nodes; skipped.")

    print(f"[Done] Analysis complete for experiment {experiment_id}.")


if __name__ == "__main__":
    main()
