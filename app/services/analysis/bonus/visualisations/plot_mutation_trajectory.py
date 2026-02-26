from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px

from app.services.analysis.bonus.database.postgres import get_connection
from app.services.analysis.bonus.mutations.trajectory import query_top_variants, build_trajectory_dataframe


def plot_mutation_trajectory(
    generation_id: int,
    top_n: int = 5,
    out_path: Path | str = "outputs/mutation_trajectory.html",
) -> Path:
    """Line chart of cumulative non-synonymous mutations vs generation for the top-N variants."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        top = query_top_variants(conn, generation_id, limit=top_n)
        if top.empty:
            raise RuntimeError("No top variants found (activity_score missing?).")

        rows = []
        for _, r in top.iterrows():
            vid = int(r["variant_id"])
            df = build_trajectory_dataframe(conn, vid)
            df["line_label"] = r["plasmid_variant_index"]
            df["final_activity_score"] = float(r["activity_score"])
            rows.append(df)

    plot_df = pd.concat(rows, ignore_index=True).sort_values(["line_label", "generation_id"])

    fig = px.line(
        plot_df,
        x="generation_id",
        y="cumulative_nonsyn",
        color="line_label",
        markers=True,
        hover_data=["variant_id", "final_activity_score"],
        title=f"Mutation Accumulation Trajectories (Top {top_n}, selected from Gen {generation_id})",
    )
    fig.update_layout(xaxis_title="Generation", yaxis_title="Cumulative non-synonymous protein mutations")

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Plot mutation accumulation trajectories for top variants.")
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--out", default="outputs/mutation_trajectory.html")
    args = ap.parse_args()

    out = plot_mutation_trajectory(args.generation_id, args.top_n, args.out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()