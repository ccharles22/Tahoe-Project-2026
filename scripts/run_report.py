from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import pandas as pd  # (kept since your pipeline returns DataFrames)

from src.analysis_MPL.database import get_conn
from src.analysis_MPL.queries import (
    fetch_wt_baselines,
    fetch_variant_raw,
    fetch_top10,
    fetch_distribution,
)
from src.analysis_MPL.activity_score import compute_stage4_metrics
from src.analysis_MPL.metrics import upsert_variant_metrics
from src.analysis_MPL.plots import plot_activity_distribution, plot_top10_table 

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


def main() -> None:
    # Require explicit experiment id so you don't accidentally run defaults.
    experiment_id = int(os.getenv("EXPERIMENT_ID", "0"))
    if experiment_id <= 0:
        raise SystemExit("Set EXPERIMENT_ID (e.g. export EXPERIMENT_ID=1)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Per-experiment output artifacts
    qc_path = OUTPUT_DIR / f"exp_{experiment_id}_stage4_qc_debug.csv"
    top10_path = OUTPUT_DIR / f"exp_{experiment_id}_top10_variants.csv"
    plot_path = OUTPUT_DIR / f"exp_{experiment_id}_activity_distribution.png"

    with get_conn() as conn:
        # 1) WT baselines
        baselines = fetch_wt_baselines(conn, experiment_id)
        print(f"[Stage4] WT baselines found for generations: {len(baselines)}")

        # 2) Raw variant metrics
        df_variants = fetch_variant_raw(conn, experiment_id)
        print(f"[Stage4] Variants fetched from DB: {len(df_variants)}")

        if df_variants.empty:
            print("[Stage4] No variants returned for this experiment_id. Exiting.")
            return

        # 3) Compute normalised metrics + activity score (with QC)
        rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)

        # ---- QC summary ----
        qc_counts = df_with_qc["qc_stage4"].value_counts(dropna=False)
        ok_n = int((df_with_qc["qc_stage4"] == "ok").sum())
        print(f"[Stage4] Total variants processed: {len(df_with_qc)}")
        print("[Stage4] QC summary:\n", qc_counts.to_string())
        print(f"[Stage4] OK variants: {ok_n}")
        print(f"[Stage4] rows_to_insert (expected OK*3): {len(rows_to_insert)}")
        # --------------------

        # 4) Upsert computed metrics into DB
        inserted_attempted = upsert_variant_metrics(conn, rows_to_insert)
        print(f"[DB] Upsert attempted rows: {inserted_attempted}")

        # Truth-check: do we have activity_score rows now?
        all_scores, exp_scores = db_count_activity_scores(conn, experiment_id)
        print(f"[DB] activity_score rows (all experiments): {all_scores}")
        print(f"[DB] activity_score rows (this experiment): {exp_scores}")

        # 5) Write QC debug CSV
        df_with_qc.to_csv(qc_path, index=False)
        print("[File] Wrote:", qc_path)

        # 6) Top-10 table
        df_top10 = fetch_top10(conn, experiment_id)
        df_top10.to_csv(top10_path, index=False)
        print("[File] Wrote:", top10_path, f"(rows={len(df_top10)})")
        plot_top10_table(df_top10, top10_path.with_suffix(".png"))
        print("[File] Wrote:", top10_path.with_suffix(".png"))

        # 7) Distribution plot data
        df_dist = fetch_distribution(conn, experiment_id)

        if df_dist.empty:
            print(
                "[Plot] No distribution data returned.\n"
                "      This usually means 0 activity_score rows for this experiment,\n"
                "      or fetch_distribution is filtering them out.\n"
                "      Check the QC CSV and the DB counts above."
            )
            return

        plot_activity_distribution(df_dist, str(plot_path))
        print("[File] Wrote:", plot_path)


if __name__ == "__main__":
    main()
