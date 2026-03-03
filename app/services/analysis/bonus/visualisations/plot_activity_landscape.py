"""Plotly-based bonus landscape visualisation for activity embeddings."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from app.services.analysis.bonus.database.postgres import get_connection


# ------------------------------------------------------------------ #
# Interpolation
# ------------------------------------------------------------------ #

def _grid_interpolate_idw(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    grid_size: int = 60,
    power: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Inverse-distance weighting (IDW) onto a regular grid.

    A higher *power* preserves local peaks better (they fall off faster
    with distance).  The default of 2.0 is a reasonable balance; use 3.0+
    when the data has sharp activity peaks you want to keep visible.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)

    # Pad the grid slightly beyond data range so edges look clean
    pad_x = (x.max() - x.min()) * 0.05
    pad_y = (y.max() - y.min()) * 0.05
    xi = np.linspace(x.min() - pad_x, x.max() + pad_x, grid_size)
    yi = np.linspace(y.min() - pad_y, y.max() + pad_y, grid_size)
    Xg, Yg = np.meshgrid(xi, yi)

    Zg = np.empty_like(Xg, dtype=float)
    eps = 1e-12

    for i in range(grid_size):
        for j in range(grid_size):
            dx = x - Xg[i, j]
            dy = y - Yg[i, j]
            d2 = dx * dx + dy * dy + eps
            w = 1.0 / (d2 ** (power / 2.0))
            Zg[i, j] = np.sum(w * z) / np.sum(w)

    return Xg, Yg, Zg


def _lookup_surface_z(
    xs: np.ndarray,
    ys: np.ndarray,
    Xg: np.ndarray,
    Yg: np.ndarray,
    Zg: np.ndarray,
) -> np.ndarray:
    """For each scatter point, find the nearest grid cell z-value so the
    dot sits exactly on the surface rather than floating above it."""
    xi = Xg[0, :]  # 1-D x ticks
    yi = Yg[:, 0]  # 1-D y ticks

    ix = np.clip(np.searchsorted(xi, xs) - 1, 0, len(xi) - 2)
    iy = np.clip(np.searchsorted(yi, ys) - 1, 0, len(yi) - 2)

    # Simple nearest-neighbour (fast, good enough at grid_size >= 60)
    return Zg[iy, ix]


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #

def plot_activity_landscape_plotly(
    generation_id: Optional[int] = None,
    method: Literal["pca", "tsne"] = "pca",
    mode: Literal["scatter", "surface"] = "scatter",
    grid_size: int = 60,
    out_path: Path | str = "outputs/activity_landscape.html",
) -> Path:
    """
    3D Plotly landscape matching the briefing Figure 4 style.

    X/Y = PCA or t-SNE diversity coordinates, Z = activity score.
    Surface mode produces a mountain-range topography with scatter dots
    sitting *on* the surface, using a warm colorscale.

    Parameters
    ----------
    generation_id : int or None
        ``None`` -> all generations.
    method : 'pca' | 'tsne'
    mode : 'scatter' | 'surface'
    grid_size : int
        Surface grid resolution.
    out_path : Path
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # ---- Fetch data ----
    # Pull coordinates from derived metrics so this works immediately after
    # precompute_embeddings_for_generation, even when embedding_runs/MVs are empty.
    x_metric = f"{method}_x"
    y_metric = f"{method}_y"
    with get_connection() as conn:
        if generation_id is not None:
            df = pd.read_sql_query(
                """
                WITH prot_mut AS (
                  SELECT
                    m.variant_id,
                    COUNT(*) AS protein_mutations
                  FROM mutations m
                  WHERE m.mutation_type = 'protein'
                    AND (m.is_synonymous IS FALSE OR m.is_synonymous IS NULL)
                  GROUP BY m.variant_id
                )
                SELECT
                  v.generation_id,
                  v.plasmid_variant_index,
                  m_activity.value AS activity_score,
                  m_x.value AS x,
                  m_y.value AS y,
                  COALESCE(pm.protein_mutations, 0) AS protein_mutations
                FROM variants v
                LEFT JOIN metrics m_activity
                  ON m_activity.variant_id = v.variant_id
                 AND m_activity.generation_id = v.generation_id
                 AND m_activity.metric_type = 'derived'
                 AND m_activity.metric_name = 'activity_score'
                LEFT JOIN metrics m_x
                  ON m_x.variant_id = v.variant_id
                 AND m_x.generation_id = v.generation_id
                 AND m_x.metric_type = 'derived'
                 AND m_x.metric_name = %s
                LEFT JOIN metrics m_y
                  ON m_y.variant_id = v.variant_id
                 AND m_y.generation_id = v.generation_id
                 AND m_y.metric_type = 'derived'
                 AND m_y.metric_name = %s
                LEFT JOIN prot_mut pm
                  ON pm.variant_id = v.variant_id
                WHERE v.generation_id = %s
                  AND m_activity.value IS NOT NULL
                """,
                conn,
                params=(x_metric, y_metric, generation_id),
            )
        else:
            df = pd.read_sql_query(
                """
                WITH prot_mut AS (
                  SELECT
                    m.variant_id,
                    COUNT(*) AS protein_mutations
                  FROM mutations m
                  WHERE m.mutation_type = 'protein'
                    AND (m.is_synonymous IS FALSE OR m.is_synonymous IS NULL)
                  GROUP BY m.variant_id
                )
                SELECT
                  v.generation_id,
                  v.plasmid_variant_index,
                  m_activity.value AS activity_score,
                  m_x.value AS x,
                  m_y.value AS y,
                  COALESCE(pm.protein_mutations, 0) AS protein_mutations
                FROM variants v
                LEFT JOIN metrics m_activity
                  ON m_activity.variant_id = v.variant_id
                 AND m_activity.generation_id = v.generation_id
                 AND m_activity.metric_type = 'derived'
                 AND m_activity.metric_name = 'activity_score'
                LEFT JOIN metrics m_x
                  ON m_x.variant_id = v.variant_id
                 AND m_x.generation_id = v.generation_id
                 AND m_x.metric_type = 'derived'
                 AND m_x.metric_name = %s
                LEFT JOIN metrics m_y
                  ON m_y.variant_id = v.variant_id
                 AND m_y.generation_id = v.generation_id
                 AND m_y.metric_type = 'derived'
                 AND m_y.metric_name = %s
                LEFT JOIN prot_mut pm
                  ON pm.variant_id = v.variant_id
                WHERE m_activity.value IS NOT NULL
                """,
                conn,
                params=(x_metric, y_metric),
            )

    if df.empty:
        scope = f"generation_id={generation_id}" if generation_id else "all generations"
        raise RuntimeError(
            f"No rows found with activity_score + {method} coordinates for {scope}. "
            "Run analysis after sequence processing to compute derived embeddings."
        )

    df = df.dropna(subset=["x", "y", "activity_score"])
    if df.empty:
        raise RuntimeError("No usable rows after dropping NA.")

    x_arr = df["x"].to_numpy()
    y_arr = df["y"].to_numpy()
    z_arr = df["activity_score"].to_numpy()

    gen_label = f"Gen {generation_id}" if generation_id else "All Generations"

    # Warm colorscale matching the briefing figure (purple -> orange -> yellow)
    warm_colorscale = [
        [0.0, "rgb(68, 1, 84)"],       # deep purple
        [0.15, "rgb(72, 35, 116)"],     # purple
        [0.30, "rgb(64, 67, 135)"],     # blue-purple
        [0.45, "rgb(52, 94, 141)"],     # teal-blue
        [0.55, "rgb(41, 123, 142)"],    # teal
        [0.65, "rgb(45, 160, 120)"],    # green-teal
        [0.75, "rgb(94, 191, 79)"],     # green
        [0.85, "rgb(177, 213, 58)"],    # yellow-green
        [0.92, "rgb(244, 199, 41)"],    # orange-yellow
        [1.0, "rgb(253, 231, 37)"],     # bright yellow
    ]

    fig = go.Figure()

    # ---- Surface layer ----
    if mode == "surface":
        # Use a slightly higher IDW power for sharper peaks
        Xg, Yg, Zg = _grid_interpolate_idw(
            x_arr, y_arr, z_arr, grid_size=grid_size, power=2.5,
        )

        fig.add_trace(
            go.Surface(
                x=Xg,
                y=Yg,
                z=Zg,
                colorscale=warm_colorscale,
                opacity=0.92,
                showscale=True,
                colorbar=dict(
                    title=dict(text="Activity Score", side="right"),
                    thickness=15,
                    len=0.65,
                ),
                # Contours displayed ON the surface (not projected to base)
                contours=dict(
                    z=dict(
                        show=True,
                        usecolormap=True,
                        highlightcolor="white",
                        project_z=False,
                    ),
                ),
                hovertemplate=(
                    f"{method.upper()} dim 1: %{{x:.2f}}<br>"
                    f"{method.upper()} dim 2: %{{y:.2f}}<br>"
                    "Activity: %{z:.3f}<extra>Surface</extra>"
                ),
                name="Surface",
            )
        )

        # Place scatter dots ON the surface (snap z to surface height)
        z_on_surface = _lookup_surface_z(x_arr, y_arr, Xg, Yg, Zg)
        # Tiny offset so dots are visible above the surface mesh
        z_scatter = z_on_surface + (z_arr.max() - z_arr.min()) * 0.005
    else:
        z_scatter = z_arr

    # ---- Scatter overlay ----
    fig.add_trace(
        go.Scatter3d(
            x=x_arr,
            y=y_arr,
            z=z_scatter,
            mode="markers",
            text=df["plasmid_variant_index"],
            customdata=np.column_stack([
                df["protein_mutations"].fillna(""),
                df["generation_id"],
            ]),
            marker=dict(
                size=3,
                color="rgba(220, 60, 60, 0.8)" if mode == "surface" else z_arr,
                colorscale=None if mode == "surface" else warm_colorscale,
                showscale=(mode != "surface"),
                colorbar=dict(
                    title=dict(text="Activity Score"),
                    thickness=15,
                    len=0.65,
                ) if mode != "surface" else None,
                line=dict(width=0),
            ),
            hovertemplate=(
                "Variant: %{text}<br>"
                f"{method.upper()} dim 1: %{{x:.2f}}<br>"
                f"{method.upper()} dim 2: %{{y:.2f}}<br>"
                "Activity: %{z:.3f}<br>"
                "Protein muts: %{customdata[0]}<br>"
                "Generation: %{customdata[1]}<extra></extra>"
            ),
            name="Variants",
        )
    )

    title_mode = "Surface + Contours" if mode == "surface" else "Scatter"
    fig.update_layout(
        title=dict(
            text=f"3D Activity Landscape ({gen_label}, {method.upper()}, {title_mode})",
            font=dict(size=16),
        ),
        scene=dict(
            xaxis_title=f"{method.upper()} dim 1",
            yaxis_title=f"{method.upper()} dim 2",
            zaxis_title="Activity Score",
            camera=dict(eye=dict(x=1.6, y=1.2, z=0.8)),
        ),
        margin=dict(l=0, r=0, t=60, b=0),
        autosize=True,
    )

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="3D Activity Landscape: X/Y = PCA or t-SNE (diversity), Z = activity_score"
    )
    ap.add_argument(
        "--generation-id", type=int, default=None,
        help="Generation to plot. Omit to plot the entire dataset.",
    )
    ap.add_argument("--method", choices=["pca", "tsne"], default="pca")
    ap.add_argument(
        "--mode",
        choices=["scatter", "surface"],
        default="scatter",
        help="scatter = points only; surface = interpolated topography with contours + points overlay",
    )
    ap.add_argument("--grid-size", type=int, default=60, help="surface only: grid resolution")
    ap.add_argument("--out", default="outputs/activity_landscape.html")

    args = ap.parse_args()

    out = plot_activity_landscape_plotly(
        generation_id=args.generation_id,
        method=args.method,
        mode=args.mode,
        grid_size=args.grid_size,
        out_path=args.out,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
