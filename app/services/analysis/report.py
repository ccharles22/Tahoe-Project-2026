from __future__ import annotations
import os
from .database import get_conn
from .queries import (
    fetch_wt_baselines,
    fetch_variant_raw,
    fetch_top10,
    fetch_distribution,
)
from .activity_score import compute_stage4_metrics
from .metrics import upsert_variant_metrics
from .plots import plot_activity_distribution

OUTPUT_DIR = "app/static/generated"

def main():
    experiment_id = int(os.getenv("EXPERIMENT_ID", "1"))

    with get_conn() as conn:
        baselines = fetch_wt_baselines(conn, experiment_id)
        df_variants = fetch_variant_raw(conn, experiment_id)

        rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)

        inserted = upsert_variant_metrics(conn, rows_to_insert)
        print(f"Inserted/updated {inserted} computed metric rows.")

        # Export QC overview (optional but very useful)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        df_with_qc.to_csv(
            os.path.join(OUTPUT_DIR, f"stage4_qc_debug_exp_{experiment_id}.csv"),
            index=False,
        )

        # Top-10 table
        df_top10 = fetch_top10(conn, experiment_id)
        top10_path = os.path.join(OUTPUT_DIR, f"top10_variants_exp_{experiment_id}.csv")
        df_top10.to_csv(top10_path, index=False)
        print("Wrote:", top10_path)

        # Distribution plot
        df_dist = fetch_distribution(conn, experiment_id)
        plot_path = os.path.join(OUTPUT_DIR, f"activity_distribution_exp_{experiment_id}.png")
        plot_activity_distribution(df_dist, plot_path)
        print("Wrote:", plot_path)

if __name__ == "__main__":
    main()