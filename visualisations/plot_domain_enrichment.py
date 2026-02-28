from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analysis.database.postgres import get_connection


# ------------------------------------------------------------------ #
# Metric display helpers
# ------------------------------------------------------------------ #
_METRIC_LABELS = {
    "nonsyn_count": "Non-synonymous mutations",
    "nonsyn_per_residue": "Non-synonymous mutations per residue",
}


def _metric_label(metric: str) -> str:
    return _METRIC_LABELS.get(metric, metric)


def plot_domain_enrichment(
    generation_id: Optional[int] = None,
    metric: Literal["nonsyn_count", "nonsyn_per_residue"] = "nonsyn_count",
    out_path: Path | str = "outputs/domain_enrichment_heatmap.html",
) -> Path:
    """Bar chart for a single generation, or cross-generation heatmap when generation_id is None."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Fetch data, joining generations to get generation_number ----
    sql = """
      SELECT g.generation_number AS generation,
             d.domain_label,
             d.nonsyn_count,
             d.syn_count,
             d.total_protein_mutations,
             d.domain_length,
             d.nonsyn_per_residue
      FROM mv_domain_mutation_enrichment d
      JOIN generations g ON g.generation_id = d.generation_id
    """
    params: tuple = ()
    if generation_id is not None:
        sql += " WHERE d.generation_id = %s"
        params = (int(generation_id),)

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        raise RuntimeError(
            "No rows found in mv_domain_mutation_enrichment. "
            "Did you build/refresh the MV with valid protein_features (wt_id mapping)?"
        )

    # ---- Single-generation bar chart ----
    if generation_id is not None:
        gen_num = int(df["generation"].iloc[0]) if "generation" in df.columns else generation_id
        df = df.sort_values(metric, ascending=False).head(25)
        fig = px.bar(
            df,
            x=metric,
            y="domain_label",
            orientation="h",
            title=f"Domain Enrichment — Generation {gen_num}",
            hover_data=["domain_length", "syn_count", "total_protein_mutations"],
            color=metric,
            color_continuous_scale="Viridis",
        )
        fig.update_layout(
            yaxis_title="Domain / Region",
            xaxis_title=_metric_label(metric),
            plot_bgcolor="white",
            font=dict(size=12),
        )
        fig.write_html(str(out_path))
        return out_path

    # ---- Cross-generation heatmap ----
    heat = df.pivot_table(
        index="domain_label",
        columns="generation",
        values=metric,
        fill_value=0,
    )
    # Sort columns numerically (generation 1, 2, …, 10)
    heat = heat.reindex(sorted(heat.columns), axis=1)
    # Rename columns to "Gen 1", "Gen 2", etc.
    heat.columns = [f"Gen {int(c)}" for c in heat.columns]

    # Sort rows so the domain with the highest total appears at the top
    heat["_total"] = heat.sum(axis=1)
    heat = heat.sort_values("_total", ascending=True)
    heat = heat.drop(columns="_total")

    # Build the heatmap with go.Heatmap for full control
    z = heat.values
    x_labels = list(heat.columns)
    y_labels = list(heat.index)

    # Annotation text: show actual values inside cells
    annotations: list[dict] = []
    for i, y_lab in enumerate(y_labels):
        for j, x_lab in enumerate(x_labels):
            val = z[i][j]
            # Format large numbers compactly
            if metric == "nonsyn_per_residue":
                text = f"{val:.2f}" if val else ""
            else:
                text = f"{int(val):,}" if val else ""
            annotations.append(dict(
                x=x_lab,
                y=y_lab,
                text=text,
                font=dict(
                    size=10,
                    color="white" if val > (np.max(z) * 0.6) else "#333333",
                ),
                showarrow=False,
                xref="x",
                yref="y",
            ))

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=x_labels,
        y=y_labels,
        colorscale="YlOrRd",
        colorbar=dict(
            title=dict(text=_metric_label(metric), font=dict(size=12)),
            thickness=15,
            len=0.75,
        ),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Generation: %{x}<br>"
            f"{_metric_label(metric)}: " + "%{z:,}<extra></extra>"
        ),
        xgap=2,
        ygap=2,
    ))

    fig.update_layout(
        title=dict(
            text=f"Domain-level Mutation Enrichment by Generation",
            font=dict(size=16),
        ),
        xaxis=dict(
            title="Generation",
            side="bottom",
            tickangle=0,
            dtick=1,
        ),
        yaxis=dict(
            title="Domain / Region",
            autorange="reversed",
        ),
        annotations=annotations,
        plot_bgcolor="white",
        margin=dict(l=160, r=80, t=70, b=60),
        height=max(350, len(y_labels) * 60 + 120),
        width=max(600, len(x_labels) * 70 + 250),
        font=dict(family="Arial, sans-serif", size=12),
    )

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Plot domain-level mutation enrichment heatmap.")
    ap.add_argument("--generation-id", type=int, required=False, help="Optional: filter to one generation.")
    ap.add_argument("--metric", choices=["nonsyn_count", "nonsyn_per_residue"], default="nonsyn_count")
    ap.add_argument("--out", default="outputs/domain_enrichment_heatmap.html")
    args = ap.parse_args()

    out = plot_domain_enrichment(
        generation_id=args.generation_id,
        metric=args.metric,
        out_path=args.out,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()