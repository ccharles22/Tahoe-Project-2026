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


def main():
    experiment_id = int(os.getenv("EXPERIMENT_ID", "1"))
    exp_output_dir = os.path.join(OUTPUT_DIR, str(experiment_id))
    os.makedirs(exp_output_dir, exist_ok=True)

    with get_conn() as conn:
        # 1) Raw variant metrics
        df_variants = fetch_variant_raw(conn, experiment_id)
        print(f"[Stage4] Variants fetched: {len(df_variants)}")
        if df_variants.empty:
            print("[Stage4] No variants for this experiment. Exiting.")
            return

        # 2) Try WT-based scoring, fallback to median-based
        score_mode = "WT-based"
        try:
            baselines = fetch_wt_baselines(conn, experiment_id)
            print(f"[Stage4] WT baselines found: {len(baselines)} generations")
            rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)
        except Exception as e:
            score_mode = "fallback (generation-median)"
            print(f"[Stage4] WT scoring unavailable ({type(e).__name__}: {e})")
            print("[Stage4] Using fallback scoring.")
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
                plot_activity_distribution(df_dist, dist_png)
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
                plot_layered_lineage(
                    df_nodes,
                    df_edges,
                    lineage_png,
                    config=PlotConfig(
                        label_mode="top10",
                        layout_mode="pack",
                        pack_generation_height=6.0,
                        generation_band_gap=0.6,
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
