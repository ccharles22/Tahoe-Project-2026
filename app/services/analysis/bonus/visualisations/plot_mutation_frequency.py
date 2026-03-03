from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from app.services.analysis.bonus.database.postgres import get_connection


# ------------------------------------------------------------------ #
# Soft colour palette for domain background bands
# ------------------------------------------------------------------ #
_DOMAIN_COLOURS = [
    "rgba(255, 127, 14, 0.15)",   # orange
    "rgba(44,  160, 44, 0.15)",   # green
    "rgba(31,  119, 180, 0.15)",  # blue
    "rgba(214, 39,  40, 0.15)",   # red
    "rgba(148, 103, 189, 0.15)",  # purple
    "rgba(140, 86,  75, 0.15)",   # brown
]


def _domain_colour(idx: int) -> str:
    return _DOMAIN_COLOURS[idx % len(_DOMAIN_COLOURS)]


# ------------------------------------------------------------------ #
# Data fetching
# ------------------------------------------------------------------ #

def fetch_mutation_counts(conn) -> pd.DataFrame:
    """Count non-synonymous protein mutations per position across all
    variants, broken down by generation_number."""
    return pd.read_sql_query(
        """
        SELECT m.position,
               g.generation_number,
               COUNT(*) AS mut_count
        FROM mutations m
        JOIN variants v ON v.variant_id = m.variant_id
        JOIN generations g ON g.generation_id = v.generation_id
        WHERE m.mutation_type = 'protein'
          AND (m.is_synonymous IS FALSE OR m.is_synonymous IS NULL)
        GROUP BY m.position, g.generation_number
        ORDER BY m.position, g.generation_number
        """,
        conn,
    )


def fetch_mutation_counts_for_generation(conn, generation_id: int) -> pd.DataFrame:
    """Count non-synonymous protein mutations per position for one generation."""
    return pd.read_sql_query(
        """
        SELECT m.position,
               g.generation_number,
               COUNT(*) AS mut_count
        FROM mutations m
        JOIN variants v ON v.variant_id = m.variant_id
        JOIN generations g ON g.generation_id = v.generation_id
        WHERE m.mutation_type = 'protein'
          AND (m.is_synonymous IS FALSE OR m.is_synonymous IS NULL)
          AND g.generation_id = %s
        GROUP BY m.position, g.generation_number
        ORDER BY m.position, g.generation_number
        """,
        conn,
        params=(generation_id,),
    )


def fetch_domain_regions(conn) -> pd.DataFrame:
    """Retrieve protein feature/domain regions for annotation."""
    try:
        return pd.read_sql_query(
            """
            SELECT DISTINCT
                   COALESCE(pf.description, pf.feature_type) AS domain_label,
                   pf.start_position,
                   pf.end_position
            FROM protein_features pf
            ORDER BY pf.start_position
            """,
            conn,
        )
    except Exception:
        conn.rollback()
        return pd.DataFrame()


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #

def plot_mutation_frequency(
    generation_id: Optional[int] = None,
    out_path: Path | str = "outputs/mutation_frequency_by_position.html",
    show_domains: bool = True,
) -> Path:
    """Two-panel mutation frequency plot:

    Top panel - Total non-synonymous mutation count per position
                (all generations combined), single colour.
    Bottom panel - Same data stacked by generation for breakdown.

    Both panels share the x-axis and show optional domain background bands.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        if generation_id is not None:
            df = fetch_mutation_counts_for_generation(conn, generation_id)
        else:
            df = fetch_mutation_counts(conn)
        domains = fetch_domain_regions(conn) if show_domains else pd.DataFrame()

    if df.empty:
        raise RuntimeError("No non-synonymous protein mutations found in the mutations table.")

    # Aggregate total per position
    totals = df.groupby("position")["mut_count"].sum().reset_index()
    totals.columns = ["position", "total"]
    totals = totals.sort_values("position")

    # ---- Generation colour palette (matches fingerprint plot) ----
    _GEN_COLOURS = [
        "#2ca02c",  # gen 1 - green
        "#1f77b4",  # gen 2 - blue
        "#ff7f0e",  # gen 3 - orange
        "#d62728",  # gen 4 - red
        "#9467bd",  # gen 5 - purple
        "#8c564b",  # gen 6 - brown
        "#e377c2",  # gen 7 - pink
        "#17becf",  # gen 8 - cyan
        "#bcbd22",  # gen 9 - olive
        "#7f7f7f",  # gen 10 - grey
    ]

    # ---- Create two-row subplot (shared x-axis) ----
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

    # ---- Domain background bands (applied to both rows) ----
    # Labels are shown via invisible hover traces instead of text
    # annotations to avoid overlapping with bar/area data.
    if not domains.empty:
        for i, row in domains.iterrows():
            # Domain bands on bottom panel only
            fig.add_vrect(
                x0=row["start_position"],
                x1=row["end_position"],
                fillcolor=_domain_colour(i),
                layer="below",
                line_width=0,
                row=2,
                col=1,
            )
            # Hover-only trace so the domain name appears on mouseover
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

    # ---- TOP PANEL: Total frequency (single colour) ----
    fig.add_trace(
        go.Bar(
            x=totals["position"],
            y=totals["total"],
            marker_color="#1f77b4",
            name="Total",
            showlegend=False,
            hovertemplate=(
                "Position: %{x}<br>"
                "Total mutations: %{y:,}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    # Top-5 hotspot annotations on the total panel
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

    # ---- BOTTOM PANEL: Stacked area by generation ----
    # Pivot to a full position x generation matrix so the area chart
    # has a value at every position (fill gaps with 0).
    all_positions = sorted(df["position"].unique())
    generations = sorted(df["generation_number"].unique())

    pivot = df.pivot_table(
        index="position", columns="generation_number",
        values="mut_count", fill_value=0,
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
                fillcolor=colour.replace(")", ", 0.7)").replace("rgb", "rgba")
                    if colour.startswith("rgb") else colour,
                stackgroup="gen",
                legendgroup=f"gen{gen}",
                hovertemplate=(
                    "Position: %{x}<br>"
                    f"Generation {gen}: " + "%{y:,}<br>"
                    "<extra></extra>"
                ),
            ),
            row=2,
            col=1,
        )

    # ---- Layout ----
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

    # Shared x-axis label on the bottom panel only
    fig.update_xaxes(
        title_text="Amino Acid Position",
        range=[-5, max_pos + 5],
        dtick=50,
        row=2, col=1,
    )
    fig.update_xaxes(range=[-5, max_pos + 5], row=1, col=1)

    fig.update_yaxes(title_text="Total Mutations", row=1, col=1)
    fig.update_yaxes(title_text="Mutations (by Generation)", row=2, col=1)

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="Plot mutation frequency by amino acid position (stacked by generation)."
    )
    ap.add_argument("--generation-id", type=int, default=None)
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
