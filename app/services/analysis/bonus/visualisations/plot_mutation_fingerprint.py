from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.services.analysis.bonus.database.postgres import get_connection


# ------------------------------------------------------------------ #
# Colour palette --- one distinct colour per generation (up to 12)
# ------------------------------------------------------------------ #
_GEN_COLOURS = [
    "#2ca02c",  # gen 1  --- green
    "#1f77b4",  # gen 2  --- blue
    "#ff7f0e",  # gen 3  --- orange
    "#d62728",  # gen 4  --- red
    "#9467bd",  # gen 5  --- purple
    "#8c564b",  # gen 6  --- brown
    "#e377c2",  # gen 7  --- pink
    "#17becf",  # gen 8  --- cyan
    "#bcbd22",  # gen 9  --- olive
    "#7f7f7f",  # gen 10 --- grey
    "#aec7e8",  # gen 11
    "#ffbb78",  # gen 12
]


def _colour_for_gen(gen: int) -> str:
    return _GEN_COLOURS[(gen - 1) % len(_GEN_COLOURS)]


# ------------------------------------------------------------------ #
# Data helpers (unchanged logic, cleaner SQL)
# ------------------------------------------------------------------ #

def fetch_lineage(conn, variant_id: int) -> pd.DataFrame:
    """Recursive CTE: leaf-to-root ancestor chain.

    Returns generation_number (1-based ordinal) instead of the raw
    generation_id primary key so that legends read "Generation 1"
    rather than an opaque database ID.
    """
    return pd.read_sql_query(
        """
        WITH RECURSIVE chain AS (
          SELECT v.variant_id, v.parent_variant_id, v.generation_id, 0 AS depth
          FROM variants v
          WHERE v.variant_id = %s
          UNION ALL
          SELECT p.variant_id, p.parent_variant_id, p.generation_id, c.depth + 1
          FROM chain c
          JOIN variants p ON p.variant_id = c.parent_variant_id
          WHERE c.parent_variant_id IS NOT NULL
        )
        SELECT c.variant_id,
               c.parent_variant_id,
               c.generation_id,
               g.generation_number,
               c.depth
        FROM chain c
        JOIN generations g ON g.generation_id = c.generation_id
        ORDER BY c.depth DESC
        """,
        conn,
        params=(variant_id,),
    )


def fetch_mutations_for_variants(conn, variant_ids: list[int]) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT variant_id, position, original, mutated
        FROM mutations
        WHERE mutation_type = 'protein'
          AND (is_synonymous IS FALSE OR is_synonymous IS NULL)
          AND variant_id = ANY(%s)
        """,
        conn,
        params=(variant_ids,),
    )


def fetch_protein_length(conn, variant_id: int) -> Optional[int]:
    """Try to determine protein length from the database.

    Falls back to the maximum mutation position + a small buffer.
    """
    try:
        df = pd.read_sql_query(
            """
            SELECT LENGTH(s.protein_seq) AS plen
            FROM sequences s
            JOIN variants v ON v.sequence_id = s.sequence_id
            WHERE v.variant_id = %s
            LIMIT 1
            """,
            conn,
            params=(variant_id,),
        )
        if not df.empty and df["plen"].iloc[0]:
            return int(df["plen"].iloc[0])
    except Exception:
        # Roll back the failed transaction so the connection stays usable
        conn.rollback()
    return None


def compute_introduction_generation(chain: pd.DataFrame, muts: pd.DataFrame) -> pd.DataFrame:
    """Walk root-to-leaf and record the generation each mutation first appeared.

    Vectorised: merge mutations with the chain to get each mutation's
    generation, then keep only the earliest (root-most) generation per
    unique (position, original, mutated) triple.
    """
    if muts.empty:
        return pd.DataFrame()

    # Map variant_id --- generation_number and depth from the chain
    chain_map = chain[["variant_id", "generation_number", "depth"]].copy()

    merged = muts.merge(chain_map, on="variant_id", how="inner")

    # The root-most ancestor has the *highest* depth value (ordered root-first).
    # We want the first generation a mutation appeared, which corresponds to the
    # node closest to the root --- highest depth.
    merged = merged.sort_values("depth", ascending=False)

    out = (
        merged
        .drop_duplicates(subset=["position", "original", "mutated"], keep="first")
        .rename(columns={"generation_number": "introduced_generation"})
        [["position", "original", "mutated", "introduced_generation"]]
        .copy()
    )

    if out.empty:
        return out

    out["label"] = out["original"] + ">" + out["mutated"] + "\n(m)"
    out["full_label"] = out["original"] + out["position"].astype(str) + out["mutated"]
    return out.sort_values(["introduced_generation", "position"])


# ------------------------------------------------------------------ #
# Vertical stacking logic --- avoids label overlap
# ------------------------------------------------------------------ #

def _assign_stacking_rows(df: pd.DataFrame, min_gap: float = 30.0) -> pd.DataFrame:
    """Assign a y-row (0, 1, 2, ...) to each mutation so close positions
    don't overlap.  Uses a simple greedy algorithm."""
    df = df.sort_values("position").copy()
    rows: list[int] = []
    row_last_x: dict[int, float] = {}  # row -> last occupied x

    for pos in df["position"]:
        placed = False
        for r in sorted(row_last_x.keys()):
            if pos - row_last_x[r] >= min_gap:
                row_last_x[r] = pos
                rows.append(r)
                placed = True
                break
        if not placed:
            new_row = len(row_last_x)
            row_last_x[new_row] = pos
            rows.append(new_row)

    df["_row"] = rows
    return df


# ------------------------------------------------------------------ #
# Main plot function
# ------------------------------------------------------------------ #

def plot_mutation_fingerprint(
    variant_id: int,
    out_path: Path | str = "outputs/mutation_fingerprint.html",
    protein_length: Optional[int] = None,
) -> Optional[Path]:
    """Mutation fingerprint plot matching the briefing Figure 3 style.

    - Downward-pointing triangles at each mutation position
    - Colour = generation the mutation was first introduced
    - Labels showing amino-acid change (e.g. Y>N)
    - Gray protein bar at the base
    - Vertical stacking to avoid overlap
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        chain = fetch_lineage(conn, variant_id)
        if chain.empty:
            raise RuntimeError("Variant not found.")

        lineage_ids = chain["variant_id"].astype(int).tolist()
        muts = fetch_mutations_for_variants(conn, lineage_ids)

        if protein_length is None:
            protein_length = fetch_protein_length(conn, variant_id)

    df = compute_introduction_generation(chain, muts)
    if df.empty:
        print(f"[fingerprint] No non-synonymous protein mutations found for variant {variant_id} lineage. Skipping.")
        return None

    # Determines protein length for the bar
    max_pos = int(df["position"].max())
    if protein_length is None or protein_length < max_pos:
        protein_length = max_pos + 20  # small buffer

    # Stacking --- use a wider gap so text labels don't collide.
    # The gap accounts for label width (~5-6 chars at font 9) which
    # needs roughly 8% of protein length, with a floor of 40 residues.
    n_muts = len(df)
    min_gap = max(40.0, protein_length * 0.08)
    df = _assign_stacking_rows(df, min_gap=min_gap)
    max_row = int(df["_row"].max())

    # When there are many mutations, hide inline text labels and rely
    # on hover instead, to keep the plot readable.
    _LABEL_THRESHOLD = 25
    show_text = n_muts <= _LABEL_THRESHOLD

    # Y coordinates: protein bar at y=0, mutations stack upward
    bar_y = 0
    bar_height = 0.4
    marker_base_y = bar_y + bar_height + 0.3  # just above the bar
    # Tighter row spacing when many rows to keep the figure manageable
    row_spacing = 1.2 if max_row <= 6 else 1.0

    df["y"] = marker_base_y + df["_row"] * row_spacing

    # ---- Build figure ----
    fig = go.Figure()

    # Gray protein bar
    fig.add_shape(
        type="rect",
        x0=0, x1=protein_length,
        y0=bar_y, y1=bar_y + bar_height,
        fillcolor="#d3d3d3",
        line=dict(color="#aaaaaa", width=1),
        layer="below",
    )

    # One trace per generation for a clean discrete legend
    generations = sorted(df["introduced_generation"].unique())
    for gen in generations:
        gen_df = df[df["introduced_generation"] == gen]
        colour = _colour_for_gen(gen)

        # Triangles --- show text labels only when mutation count is low
        marker_size = 14 if n_muts <= 40 else 10
        fig.add_trace(go.Scatter(
            x=gen_df["position"],
            y=gen_df["y"],
            mode="markers+text" if show_text else "markers",
            marker=dict(
                symbol="triangle-down",
                size=marker_size,
                color=colour,
                line=dict(color="black", width=0.5),
            ),
            text=gen_df["label"] if show_text else None,
            textposition="top center" if show_text else None,
            textfont=dict(size=9) if show_text else None,
            name=f"Generation {gen}",
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Position: %{x}<br>"
                "Type: Missense<br>"
                "Generation introduced: %{customdata[1]}<extra></extra>"
            ),
            customdata=np.column_stack([
                gen_df["full_label"].values,
                gen_df["introduced_generation"].values,
            ]),
        ))

        # Vertical dashed lines --- one batched trace instead of per-row add_shape
        n = len(gen_df)
        positions = gen_df["position"].values
        y_vals = gen_df["y"].values
        bar_top = bar_y + bar_height

        # Each line segment: (x, bar_top) --- (x, y) separated by None
        xs = np.empty(n * 3, dtype=object)
        ys = np.empty(n * 3, dtype=object)
        xs[0::3] = positions
        xs[1::3] = positions
        xs[2::3] = None
        ys[0::3] = bar_top
        ys[1::3] = y_vals
        ys[2::3] = None

        fig.add_trace(go.Scatter(
            x=xs,
            y=ys,
            mode="lines",
            line=dict(color=colour, width=1, dash="dot"),
            showlegend=False,
            hoverinfo="skip",
        ))

    # Layout
    y_top = marker_base_y + (max_row + 1) * row_spacing + 0.5
    fig.update_layout(
        title=dict(
            text=f"Mutation Fingerprint --- Variant {variant_id}",
            font=dict(size=16),
        ),
        xaxis=dict(
            title="Amino Acid Position",
            range=[-10, protein_length + 10],
            showgrid=False,
        ),
        yaxis=dict(
            visible=False,
            range=[-0.5, y_top],
        ),
        legend=dict(
            title="Generation introduced",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
        ),
        plot_bgcolor="white",
        margin=dict(l=20, r=160, t=60, b=50),
        height=max(350, 200 + max_row * 70),
    )

    fig.write_html(str(out_path))
    return out_path


# ------------------------------------------------------------------ #
# Combined multi-variant fingerprint
# ------------------------------------------------------------------ #

def plot_mutation_fingerprints(
    variant_ids: list[int],
    out_path: Path | str = "outputs/mutation_fingerprint_combined.html",
    protein_length: Optional[int] = None,
) -> Optional[Path]:
    """Combined fingerprint plot: one horizontal lane per variant, all in
    a single figure.

    Each lane contains its own grey protein bar with mutation markers
    stacked above it.  Lanes are separated vertically and labelled on the
    left with the variant ID.  A shared generation colour legend appears
    once on the right.

    Parameters
    ----------
    variant_ids : list[int]
        Variant IDs to include (order is preserved top-to-bottom).
    out_path : path
        Output HTML file.
    protein_length : int or None
        If ``None``, derived from the data.
    """
    if not variant_ids:
        print("[fingerprint] No variant IDs provided. Skipping.")
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Collect per-variant data ----
    variant_data: list[tuple[int, pd.DataFrame, int]] = []  # (vid, df, plen)

    with get_connection() as conn:
        for vid in variant_ids:
            chain = fetch_lineage(conn, vid)
            if chain.empty:
                continue
            lineage_ids = chain["variant_id"].astype(int).tolist()
            muts = fetch_mutations_for_variants(conn, lineage_ids)
            df = compute_introduction_generation(chain, muts)
            if df.empty:
                continue

            plen = protein_length
            if plen is None:
                plen = fetch_protein_length(conn, vid)
            max_pos = int(df["position"].max())
            if plen is None or plen < max_pos:
                plen = max_pos + 20

            variant_data.append((vid, df, plen))

    if not variant_data:
        print("[fingerprint] No mutations found for any of the requested variants. Skipping.")
        return None

    # Use the widest protein length across all variants for a shared x-axis
    shared_plen = max(plen for _, _, plen in variant_data)

    # ---- Layout constants ----
    bar_height = 0.4
    intra_lane_base = 0.3          # gap between bar top and first marker row
    inter_lane_gap = 1.5           # vertical space between lanes

    fig = go.Figure()
    seen_gens: set[int] = set()    # track which generations already have a legend entry
    annotations: list[dict] = []
    y_cursor = 0.0                 # tracks the bottom of the next lane

    for lane_idx, (vid, df, _plen) in enumerate(variant_data):
        # Stacking within this lane
        n_muts = len(df)
        min_gap = max(40.0, shared_plen * 0.08)
        df = _assign_stacking_rows(df, min_gap=min_gap)
        max_row = int(df["_row"].max())

        _LABEL_THRESHOLD = 20
        show_text = n_muts <= _LABEL_THRESHOLD
        marker_size = 14 if n_muts <= 40 else 10

        row_spacing = 1.2 if max_row <= 6 else 1.0

        bar_y = y_cursor
        bar_top = bar_y + bar_height
        marker_base_y = bar_top + intra_lane_base
        df["y"] = marker_base_y + df["_row"] * row_spacing
        lane_top = marker_base_y + (max_row + 1) * row_spacing

        # Grey protein bar
        fig.add_shape(
            type="rect",
            x0=0, x1=shared_plen,
            y0=bar_y, y1=bar_top,
            fillcolor="#d3d3d3",
            line=dict(color="#aaaaaa", width=1),
            layer="below",
        )

        # Variant label on the left
        annotations.append(dict(
            x=-5,
            y=bar_y + bar_height / 2,
            text=f"<b>Variant {vid}</b>",
            showarrow=False,
            xanchor="right",
            yanchor="middle",
            font=dict(size=10),
        ))

        # Generation traces
        generations = sorted(df["introduced_generation"].unique())
        for gen in generations:
            gen_df = df[df["introduced_generation"] == gen]
            colour = _colour_for_gen(gen)
            show_legend = gen not in seen_gens
            seen_gens.add(gen)

            fig.add_trace(go.Scatter(
                x=gen_df["position"],
                y=gen_df["y"],
                mode="markers+text" if show_text else "markers",
                marker=dict(
                    symbol="triangle-down",
                    size=marker_size,
                    color=colour,
                    line=dict(color="black", width=0.5),
                ),
                text=gen_df["label"] if show_text else None,
                textposition="top center" if show_text else None,
                textfont=dict(size=9) if show_text else None,
                name=f"Generation {gen}",
                legendgroup=f"gen{gen}",
                showlegend=show_legend,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Variant: %{customdata[2]}<br>"
                    "Position: %{x}<br>"
                    "Type: Missense<br>"
                    "Generation introduced: %{customdata[1]}<extra></extra>"
                ),
                customdata=np.column_stack([
                    gen_df["full_label"].values,
                    gen_df["introduced_generation"].values,
                    np.full(len(gen_df), vid),
                ]),
            ))

            # Dashed lines (batched)
            n = len(gen_df)
            positions = gen_df["position"].values
            y_vals = gen_df["y"].values
            xs = np.empty(n * 3, dtype=object)
            ys = np.empty(n * 3, dtype=object)
            xs[0::3] = positions
            xs[1::3] = positions
            xs[2::3] = None
            ys[0::3] = bar_top
            ys[1::3] = y_vals
            ys[2::3] = None

            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="lines",
                line=dict(color=colour, width=1, dash="dot"),
                showlegend=False,
                hoverinfo="skip",
            ))

        # Advance cursor for the next lane
        y_cursor = lane_top + inter_lane_gap

    # ---- Layout ----
    n_variants = len(variant_data)
    fig.update_layout(
        title=dict(
            text=f"Mutation Fingerprints --- {n_variants} Variants",
            font=dict(size=16),
        ),
        xaxis=dict(
            title="Amino Acid Position",
            range=[-max(80, shared_plen * 0.12), shared_plen + 10],
            showgrid=False,
        ),
        yaxis=dict(
            visible=False,
            range=[-0.5, y_cursor + 0.5],
        ),
        legend=dict(
            title="Generation introduced",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
        ),
        annotations=annotations,
        plot_bgcolor="white",
        margin=dict(l=100, r=160, t=60, b=50),
        height=max(400, int(y_cursor * 55) + 120),
    )

    fig.write_html(str(out_path))
    return out_path


# ------------------------------------------------------------------ #
# Interactive dropdown variant selector
# ------------------------------------------------------------------ #

def plot_mutation_fingerprint_dropdown(
    variant_ids: list[int],
    out_path: Path | str = "outputs/mutation_fingerprint_selector.html",
    protein_length: Optional[int] = None,
) -> Optional[Path]:
    """Single-view fingerprint with a dropdown to select which variant to
    display.  This directly matches the brief requirement: "Enable users
    to **select** any of these top 10 performing variants."

    All variants share the same axes and protein bar; the dropdown
    toggles which variant's mutation markers are visible.

    Parameters
    ----------
    variant_ids : list[int]
        Variant IDs to include in the dropdown.
    out_path : Path or str
        Output HTML file.
    protein_length : int or None
        If `None`, derived from the data.
    """
    if not variant_ids:
        print("[fingerprint] No variant IDs provided. Skipping.")
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Collect per-variant data ----
    variant_data: list[tuple[int, pd.DataFrame, int]] = []

    with get_connection() as conn:
        for vid in variant_ids:
            chain = fetch_lineage(conn, vid)
            if chain.empty:
                continue
            lineage_ids = chain["variant_id"].astype(int).tolist()
            muts = fetch_mutations_for_variants(conn, lineage_ids)
            df = compute_introduction_generation(chain, muts)
            if df.empty:
                continue

            plen = protein_length
            if plen is None:
                plen = fetch_protein_length(conn, vid)
            max_pos = int(df["position"].max())
            if plen is None or plen < max_pos:
                plen = max_pos + 20

            variant_data.append((vid, df, plen))

    if not variant_data:
        print("[fingerprint] No mutations found for any of the requested variants. Skipping.")
        return None

    shared_plen = max(p for _, _, p in variant_data)

    # ---- Build all traces, tracking which belong to which variant ----
    fig = go.Figure()

    # Grey protein bar (always visible)
    bar_y = 0
    bar_height = 0.4
    bar_top = bar_y + bar_height
    fig.add_shape(
        type="rect",
        x0=0, x1=shared_plen,
        y0=bar_y, y1=bar_top,
        fillcolor="#d3d3d3",
        line=dict(color="#aaaaaa", width=1),
        layer="below",
    )

    # For each variant, compute layout and add traces.
    # Record the global trace indices that belong to each variant so
    # the dropdown can toggle visibility.
    trace_groups: list[list[int]] = []   # trace_groups[i] = list of trace indices for variant i
    all_y_tops: list[float] = []
    trace_idx = 0

    for vid, df, _plen in variant_data:
        group_indices: list[int] = []

        n_muts = len(df)
        min_gap = max(40.0, shared_plen * 0.08)
        df = _assign_stacking_rows(df, min_gap=min_gap)
        max_row = int(df["_row"].max())

        _LABEL_THRESHOLD = 25
        show_text = n_muts <= _LABEL_THRESHOLD
        marker_size = 14 if n_muts <= 40 else 10
        row_spacing = 1.2 if max_row <= 6 else 1.0

        marker_base_y = bar_top + 0.3
        df["y"] = marker_base_y + df["_row"] * row_spacing
        y_top = marker_base_y + (max_row + 1) * row_spacing + 0.5
        all_y_tops.append(y_top)

        generations = sorted(df["introduced_generation"].unique())
        for gen in generations:
            gen_df = df[df["introduced_generation"] == gen]
            colour = _colour_for_gen(gen)

            # Marker trace
            fig.add_trace(go.Scatter(
                x=gen_df["position"],
                y=gen_df["y"],
                mode="markers+text" if show_text else "markers",
                marker=dict(
                    symbol="triangle-down",
                    size=marker_size,
                    color=colour,
                    line=dict(color="black", width=0.5),
                ),
                text=gen_df["label"] if show_text else None,
                textposition="top center" if show_text else None,
                textfont=dict(size=9) if show_text else None,
                name=f"Generation {gen}",
                legendgroup=f"gen{gen}",
                visible=(vid == variant_data[0][0]),  # first variant visible initially
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Variant: %{customdata[2]}<br>"
                    "Position: %{x}<br>"
                    "Type: Missense<br>"
                    "Generation introduced: %{customdata[1]}<extra></extra>"
                ),
                customdata=np.column_stack([
                    gen_df["full_label"].values,
                    gen_df["introduced_generation"].values,
                    np.full(len(gen_df), vid),
                ]),
            ))
            group_indices.append(trace_idx)
            trace_idx += 1

            # Dashed line trace
            n = len(gen_df)
            positions = gen_df["position"].values
            y_vals = gen_df["y"].values
            xs = np.empty(n * 3, dtype=object)
            ys = np.empty(n * 3, dtype=object)
            xs[0::3] = positions
            xs[1::3] = positions
            xs[2::3] = None
            ys[0::3] = bar_top
            ys[1::3] = y_vals
            ys[2::3] = None

            fig.add_trace(go.Scatter(
                x=xs, y=ys,
                mode="lines",
                line=dict(color=colour, width=1, dash="dot"),
                showlegend=False,
                hoverinfo="skip",
                visible=(vid == variant_data[0][0]),
            ))
            group_indices.append(trace_idx)
            trace_idx += 1

        trace_groups.append(group_indices)

    total_traces = trace_idx

    # ---- Build dropdown buttons ----
    # For the generation legend to work correctly, we need to show
    # legend entries only for the active variant. We handle this by
    # controlling showlegend via the visibility array.
    buttons = []
    for var_idx, (vid, _df, _plen) in enumerate(variant_data):
        visibility = [False] * total_traces
        for ti in trace_groups[var_idx]:
            visibility[ti] = True

        # Determine which legend groups are present for this variant
        # so we can set showlegend correctly.
        active_traces = trace_groups[var_idx]

        buttons.append(dict(
            label=f"Variant {vid}",
            method="update",
            args=[
                {"visible": visibility},
                {
                    "title.text": f"Mutation Fingerprint --- Variant {vid}  (colored by generation introduced)",
                    "yaxis.range": [-0.5, all_y_tops[var_idx]],
                },
            ],
        ))

    # ---- Layout ----
    first_y_top = all_y_tops[0] if all_y_tops else 5

    fig.update_layout(
        title=dict(
            text=f"Mutation Fingerprint --- Variant {variant_data[0][0]}  (colored by generation introduced)",
            font=dict(size=16),
        ),
        xaxis=dict(
            title="Amino Acid Position",
            range=[-10, shared_plen + 10],
            showgrid=False,
        ),
        yaxis=dict(
            visible=False,
            range=[-0.5, first_y_top],
        ),
        legend=dict(
            title="Generation introduced",
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
        ),
        updatemenus=[
            dict(
                active=0,
                buttons=buttons,
                direction="down",
                showactive=True,
                x=0.0,
                xanchor="left",
                y=1.15,
                yanchor="top",
                bgcolor="white",
                bordercolor="#cccccc",
                font=dict(size=12),
                pad=dict(r=10, t=10),
            ),
        ],
        annotations=[
            dict(
                text="Select variant:",
                x=0.0,
                xref="paper",
                xanchor="right",
                xshift=-10,
                y=1.13,
                yref="paper",
                yanchor="top",
                showarrow=False,
                font=dict(size=13),
            ),
        ],
        plot_bgcolor="white",
        margin=dict(l=20, r=160, t=90, b=50),
        height=500,
    )

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Mutation fingerprint plot coloured by generation introduced.")
    ap.add_argument("--variant-id", type=int, required=False, default=None,
                     help="Single variant (legacy). Prefer --variant-ids for combined plot.")
    ap.add_argument("--variant-ids", type=int, nargs="+", default=None,
                     help="One or more variant IDs for a combined fingerprint plot.")
    ap.add_argument("--out", default="outputs/mutation_fingerprint.html")
    args = ap.parse_args()

    if args.variant_ids:
        out = plot_mutation_fingerprints(args.variant_ids, args.out)
    elif args.variant_id:
        out = plot_mutation_fingerprint(args.variant_id, args.out)
    else:
        ap.error("Provide --variant-id or --variant-ids.")

    if out:
        print(f"Wrote {out}")
    else:
        print("Fingerprint skipped (no mutations).")


if __name__ == "__main__":
    main()
