from __future__ import annotations

import os

from src.analysis_MPL.database import get_conn
from src.analysis_MPL.queries import (
    fetch_wt_baselines,
    fetch_variant_raw,
    fetch_top10,
    fetch_distribution,
)
from src.analysis_MPL.activity_score import compute_stage4_metrics
from src.analysis_MPL.metrics import upsert_variant_metrics
from src.analysis_MPL.plots import plot_activity_distribution

OUTPUT_DIR = "app/static/generated"


def main() -> None:
    # Select which experiment to analyse (default = 1)
    experiment_id = int(os.getenv("EXPERIMENT_ID", "1"))

    with get_conn() as conn:
        # 1) WT baselines (strict: fetch_wt_baselines will raise if none exist)
        baselines = fetch_wt_baselines(conn, experiment_id)
        print(f"WT baselines found for generations: {len(baselines)}")

        # 2) Pull raw variant metrics for this experiment
        df_variants = fetch_variant_raw(conn, experiment_id)
        print(f"Variants fetched from DB: {len(df_variants)}")

        # 3) Compute normalised metrics + activity score (with QC)
        rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)

        # ---- QC summary ----
        print(f"Total variants processed: {len(df_with_qc)}")
        print("Stage 4 QC summary:")
        print(df_with_qc["qc_stage4"].value_counts())
        # --------------------

        # 4) Upsert computed metrics into DB
        inserted = upsert_variant_metrics(conn, rows_to_insert)
        print(f"Inserted/updated {inserted} computed metric rows.")

        # 5) Export QC overview for debugging / audit
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        qc_path = os.path.join(OUTPUT_DIR, "stage4_qc_debug.csv")
        df_with_qc.to_csv(qc_path, index=False)
        print("Wrote:", qc_path)

        # 6) Top-10 table
        df_top10 = fetch_top10(conn, experiment_id)
        top10_path = os.path.join(OUTPUT_DIR, "top10_variants.csv")
        df_top10.to_csv(top10_path, index=False)
        print("Wrote:", top10_path)

        # 7) Activity score distribution plot per generation
        df_dist = fetch_distribution(conn, experiment_id)
        plot_path = os.path.join(OUTPUT_DIR, "activity_distribution.png")
        plot_activity_distribution(df_dist, plot_path)
        print("Wrote:", plot_path)


if __name__ == "__main__":
    main()