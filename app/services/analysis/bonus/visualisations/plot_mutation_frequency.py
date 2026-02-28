from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.services.analysis.bonus.database.postgres import get_connection


_DOMAIN_COLOURS = [
    "rgba(255, 127, 14, 0.15)",
    "rgba(44, 160, 44, 0.15)",
    "rgba(31, 119, 180, 0.15)",
    "rgba(214, 39, 40, 0.15)",
    "rgba(148, 103, 189, 0.15)",
    "rgba(140, 86, 75, 0.15)",
]

_GEN_COLOURS = [
    "#2ca02c",
    "#1f77b4",
    "#ff7f0e",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
    "#bcbd22",
    "#7f7f7f",
]


def _domain_colour(idx: int) -> str:
    return _DOMAIN_COLOURS[idx % len(_DOMAIN_COLOURS)]


def fetch_mutation_counts(conn, generation_id: int) -> pd.DataFrame:
    """Count non-synonymous protein mutations per position across one experiment."""
    return pd.read_sql_query(
        """
        WITH target_experiment AS (
            SELECT experiment_id
            FROM generations
            WHERE generation_id = %s
        )
        SELECT
            m.position,
            g.generation_number,
            COUNT(*) AS mut_count
        FROM mutations m
        JOIN variants v ON v.variant_id = m.variant_id
        JOIN generations g ON g.generation_id = v.generation_id
        WHERE m.mutation_type = 'protein'
          AND (m.is_synonymous IS FALSE OR m.is_synonymous IS NULL)
          AND g.experiment_id = (SELECT experiment_id FROM target_experiment)
        GROUP BY m.position, g.generation_number
        ORDER BY m.position, g.generation_number
        """,
        conn,
        params=(generation_id,),
    )


def fetch_domain_regions(conn, generation_id: int) -> pd.DataFrame:
    """Retrieve protein feature/domain regions for the experiment WT."""
    try:
        return pd.read_sql_query(
            """
            WITH target_experiment AS (
                SELECT experiment_id
                FROM generations
                WHERE generation_id = %s
            )
            SELECT DISTINCT
                   COALESCE(pf.description, pf.feature_type) AS domain_label,
                   pf.start_position,
                   pf.end_position
            FROM protein_features pf
            JOIN experiments e ON e.wt_id = pf.wt_id
            WHERE e.experiment_id = (SELECT experiment_id FROM target_experiment)
            ORDER BY pf.start_position
            """,
            conn,
            params=(generation_id,),
        )
    except Exception:
        conn.rollback()
        return pd.DataFrame()


def plot_mutation_frequency(
    generation_id: int,
    out_path: Path | str = "outputs/mutation_frequency_by_position.html",
    show_domains: bool = True,
) -> Path:
    """Plot experiment-scoped mutation frequency by AA position, split by generation."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        df = fetch_mutation_counts(conn, generation_id)
        domains = fetch_domain_regions(conn, generation_id) if show_domains else pd.DataFrame()

    if df.empty:
        raise RuntimeError("No non-synonymous protein mutations found for this experiment.")

    totals = df.groupby("position")["mut_count"].sum().reset_index()
    totals.columns = ["position", "total"]
    totals = totals.sort_values("position")

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.45, 0.55],
        subplot_titles=[
            "Total Non-synonymous Mutation Frequency by Position",
            "Breakdown by Generation",
        ],
    )

    max_pos = int(df["position"].max())

    if not domains.empty:
        for i, row in domains.iterrows():
            fig.add_vrect(
                x0=row["start_position"],
                x1=row["end_position"],
                fillcolor=_domain_colour(i),
                layer="below",
                line_width=0,
                row=2,
                col=1,
            )
            mid_x = (row["start_position"] + row["end_position"]) / 2
            fig.add_trace(
                go.Scatter(
                    x=[mid_x],
                    y=[0],
                    mode="markers",
                    marker=dict(size=0.1, opacity=0),
                    showlegend=False,
                    hoverinfo="text",
                    hovertext=row["domain_label"],
                ),
                row=1,
                col=1,
            )

    fig.add_trace(
        go.Bar(
            x=totals["position"],
            y=totals["total"],
            marker_color="#1f77b4",
            name="Total",
            showlegend=False,
            hovertemplate="Position: %{x}<br>Total mutations: %{y:,}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    top_positions = totals.nlargest(5, "total")
    for _, tp in top_positions.iterrows():
        fig.add_annotation(
            x=tp["position"],
            y=tp["total"],
            text=f"Pos {int(tp['position'])}",
            showarrow=True,
            arrowhead=2,
            arrowsize=0.8,
            ax=0,
            ay=-25,
            font=dict(size=9, color="#333333"),
            row=1,
            col=1,
        )

    all_positions = sorted(df["position"].unique())
    generations = sorted(df["generation_number"].unique())

    pivot = df.pivot_table(
        index="position",
        columns="generation_number",
        values="mut_count",
        fill_value=0,
    ).reindex(all_positions, fill_value=0)

    for gen in generations:
        colour = _GEN_COLOURS[(gen - 1) % len(_GEN_COLOURS)]
        y_vals = pivot[gen].values if gen in pivot.columns else [0] * len(all_positions)
        fig.add_trace(
            go.Scatter(
                x=all_positions,
                y=y_vals,
                name=f"Generation {gen}",
                mode="lines",
                line=dict(width=0.5, color=colour),
                fillcolor=colour,
                stackgroup="gen",
                legendgroup=f"gen{gen}",
                hovertemplate=(
                    "Position: %{x}<br>"
                    f"Generation {gen}: " + "%{y:,}<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        title=None,
        legend=dict(
            title="Generation",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
        ),
        plot_bgcolor="white",
        margin=dict(l=60, r=160, t=60, b=60),
        height=700,
        width=1100,
        font=dict(family="Arial, sans-serif", size=12),
        bargap=0.1,
    )
    fig.update_xaxes(title_text="Amino Acid Position", range=[-5, max_pos + 5], dtick=50, row=2, col=1)
    fig.update_xaxes(range=[-5, max_pos + 5], row=1, col=1)
    fig.update_yaxes(title_text="Total Mutations", row=1, col=1)
    fig.update_yaxes(title_text="Mutations (by Generation)", row=2, col=1)

    fig.write_html(str(out_path))
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Plot experiment-scoped mutation frequency by amino acid position."
    )
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--out", default="outputs/mutation_frequency_by_position.html")
    ap.add_argument("--no-domains", action="store_true", help="Hide domain region background bands.")
    args = ap.parse_args()

    out = plot_mutation_frequency(
        generation_id=args.generation_id,
        out_path=args.out,
        show_domains=not args.no_domains,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
