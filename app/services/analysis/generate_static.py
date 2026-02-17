from __future__ import annotations

from pathlib import Path

from .database import get_conn
from .queries import (
    fetch_top10,
    fetch_distribution,
    fetch_lineage_nodes,
    fetch_lineage_edges,
)

from .plots.top10 import plot_top10_table
from .plots.distribution import plot_activity_distribution
from .plots.lineage import plot_layered_lineage


ROOT_DIR = Path(__file__).resolve().parents[2]   # repo root
OUT_DIR = ROOT_DIR / "app" / "static" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("generate_static.py running from:", Path(__file__).resolve())
print("Writing outputs to:", OUT_DIR.resolve())


def generate_all(experiment_id: int) -> None:
    with get_conn() as conn:
        df_top10 = fetch_top10(conn, experiment_id)
        df_dist = fetch_distribution(conn, experiment_id)
        nodes = fetch_lineage_nodes(conn, experiment_id)
        edges = fetch_lineage_edges(conn, experiment_id)

    # --- skip experiments with no derived metrics ---
    if df_top10 is None or df_top10.empty:
        print(f"[skip] experiment {experiment_id}: no top10 activity_score data")
        return

    if df_dist is None or df_dist.empty:
        print(f"[skip] experiment {experiment_id}: no distribution activity_score data")
        return

    if nodes is None or nodes.empty:
        print(f"[skip] experiment {experiment_id}: no variants/generations for lineage")
        return

    plot_top10_table(df_top10, OUT_DIR / f"top10_exp{experiment_id}.png")
    plot_activity_distribution(df_dist, OUT_DIR / f"distribution_exp{experiment_id}.png")
    plot_layered_lineage(nodes, edges, OUT_DIR / f"lineage_exp{experiment_id}.png")

    print(f"[ok] experiment {experiment_id}: generated plots")



if __name__ == "__main__":
    from .queries import fetch_experiment_ids

    with get_conn() as conn:
        experiment_ids = fetch_experiment_ids(conn)

    for exp_id in experiment_ids:
        generate_all(experiment_id=exp_id)

    print(f"Generated {len(experiment_ids)} experiment(s) into: {OUT_DIR.resolve()}")
