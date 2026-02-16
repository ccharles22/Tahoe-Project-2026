from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple, List, Dict, Any

import numpy as np
import pandas as pd

from src.analysis_MPL.database import get_conn
from src.analysis_MPL.queries import (
    fetch_wt_baselines,
    fetch_variant_raw,
    fetch_top10,
    fetch_distribution,
)
from src.analysis_MPL.activity_score import compute_stage4_metrics
from src.analysis_MPL.metrics import upsert_variant_metrics
from src.analysis_MPL.plots.top10 import plot_top10_table
from src.analysis_MPL.plots.distribution import plot_activity_distribution


OUTPUT_DIR = Path("app/static/generated")


def db_count_activity_scores(conn, experiment_id: int) -> Tuple[int, int]:
    """Returns (all_activity_scores, this_experiment_activity_scores)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM metrics
            WHERE metric_name='activity_score'
              AND metric_type='derived'
              AND variant_id IS NOT NULL;
            """
        )
        all_n = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM metrics m
            JOIN variants v ON v.variant_id = m.variant_id
            JOIN generations g ON g.generation_id = v.generation_id
            WHERE m.metric_name='activity_score'
              AND m.metric_type='derived'
              AND g.experiment_id = %s;
            """,
            (experiment_id,),
        )
        exp_n = int(cur.fetchone()[0])

    return all_n, exp_n


def compute_activity_score_fallback(df_variants: pd.DataFrame) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    WT-free scoring fallback:
    - Within each generation, normalise DNA and protein yields by generation median
    - activity_score = dna_norm / protein_norm

    Returns:
      rows_to_insert: list of metric rows suitable for upsert_variant_metrics (3 per OK variant)
      df_with_qc: df_variants with computed columns and qc_stage4 labels
    """
    d = df_variants.copy()

    # Required columns
    required = {"variant_id", "generation_id", "dna_yield_raw", "protein_yield_raw"}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(f"Fallback scoring requires columns {sorted(required)}; missing {sorted(missing)}")

    # Coerce numeric
    d["dna_yield_raw"] = pd.to_numeric(d["dna_yield_raw"], errors="coerce")
    d["protein_yield_raw"] = pd.to_numeric(d["protein_yield_raw"], errors="coerce")

    # Compute per-generation medians
    d["dna_med"] = d.groupby("generation_id")["dna_yield_raw"].transform("median")
    d["prot_med"] = d.groupby("generation_id")["protein_yield_raw"].transform("median")

    # Avoid divide by zero
    d.loc[d["dna_med"] == 0, "dna_med"] = np.nan
    d.loc[d["prot_med"] == 0, "prot_med"] = np.nan

    d["dna_yield_norm"] = d["dna_yield_raw"] / d["dna_med"]
    d["protein_yield_norm"] = d["protein_yield_raw"] / d["prot_med"]
    d["activity_score"] = d["dna_yield_norm"] / d["protein_yield_norm"]

    # QC
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
        variant_id = int(r.variant_id)
        generation_id = int(r.generation_id)

        rows.append(
            dict(
                generation_id=generation_id,
                variant_id=variant_id,
                wt_control_id=None,
                metric_name="dna_yield_norm",
                metric_type="normalized",
                value=float(r.dna_yield_norm),
                unit=None,
                metric_definition_id=None,
            )
        )
        rows.append(
            dict(
                generation_id=generation_id,
                variant_id=variant_id,
                wt_control_id=None,
                metric_name="protein_yield_norm",
                metric_type="normalized",
                value=float(r.protein_yield_norm),
                unit=None,
                metric_definition_id=None,
            )
        )
        rows.append(
            dict(
                generation_id=generation_id,
                variant_id=variant_id,
                wt_control_id=None,
                metric_name="activity_score",
                metric_type="derived",
                value=float(r.activity_score),
                unit=None,
                metric_definition_id=None,
            )
        )

    return rows, d


def main() -> None:
    experiment_id = int(os.getenv("EXPERIMENT_ID", "0"))
    if experiment_id <= 0:
        raise SystemExit("Set EXPERIMENT_ID (e.g. export EXPERIMENT_ID=1)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    qc_path = OUTPUT_DIR / f"exp_{experiment_id}_stage4_qc_debug.csv"
    top10_path = OUTPUT_DIR / f"exp_{experiment_id}_top10_variants.csv"
    plot_path = OUTPUT_DIR / f"exp_{experiment_id}_activity_distribution.png"

    with get_conn() as conn:
        # 1) Raw variant metrics (needed for BOTH WT-based + fallback)
        df_variants = fetch_variant_raw(conn, experiment_id)
        print(f"[Stage4] Variants fetched from DB: {len(df_variants)}")
        if df_variants.empty:
            print("[Stage4] No variants returned for this experiment_id. Exiting.")
            return

        # 2) Try WT-based baselines first, else fallback
        score_mode = "WT-based"
        try:
            baselines = fetch_wt_baselines(conn, experiment_id)
            print(f"[Stage4] WT baselines found for generations: {len(baselines)}")

            rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)

        except Exception as e:
            # Most common expected failure: no valid WT baselines (ValueError from fetch_wt_baselines)
            score_mode = "fallback (no WT baselines)"
            print(f"[Stage4] WT-based scoring unavailable ({type(e).__name__}: {e})")
            print("[Stage4] Using fallback scoring (generation-median normalisation).")

            rows_to_insert, df_with_qc = compute_activity_score_fallback(df_variants)

        print(f"[Stage4] Activity score computed using: {score_mode}")

        # ---- QC summary ----
        if "qc_stage4" in df_with_qc.columns:
            qc_counts = df_with_qc["qc_stage4"].value_counts(dropna=False)
            ok_n = int((df_with_qc["qc_stage4"] == "ok").sum())
            print(f"[Stage4] Total variants processed: {len(df_with_qc)}")
            print("[Stage4] QC summary:\n", qc_counts.to_string())
            print(f"[Stage4] OK variants: {ok_n}")
        print(f"[Stage4] rows_to_insert: {len(rows_to_insert)} (expected ~OK*3)")
        # --------------------

        # 3) Upsert computed metrics into DB
        inserted_attempted = upsert_variant_metrics(conn, rows_to_insert)
        print(f"[DB] Upsert attempted rows: {inserted_attempted}")

        # Truth-check: do we have activity_score rows now?
        all_scores, exp_scores = db_count_activity_scores(conn, experiment_id)
        print(f"[DB] activity_score rows (all experiments): {all_scores}")
        print(f"[DB] activity_score rows (this experiment): {exp_scores}")

        # 4) Write QC debug CSV
        df_with_qc.to_csv(qc_path, index=False)
        print("[File] Wrote:", qc_path)

        # 5) Top-10 table + PNG
        df_top10 = fetch_top10(conn, experiment_id)
        df_top10.to_csv(top10_path, index=False)
        print("[File] Wrote:", top10_path, f"(rows={len(df_top10)})")

        if df_top10.empty:
            print("[Top10] No top10 rows returned (activity_score may be missing or filtered).")
        else:
            plot_top10_table(df_top10, top10_path.with_suffix(".png"))
            print("[File] Wrote:", top10_path.with_suffix(".png"))

        # 6) Distribution plot
        df_dist = fetch_distribution(conn, experiment_id)
        if df_dist.empty:
            print(
                "[Plot] No distribution data returned.\n"
                "      Check activity_score presence and the DB counts above."
            )
            return

        plot_activity_distribution(df_dist, str(plot_path))
        print("[File] Wrote:", plot_path)


if __name__ == "__main__":
    main()
