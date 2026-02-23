from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from analysis.database.postgres import get_connection


def _grid_interpolate_idw(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    grid_size: int = 60,
    power: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Inverse-distance weighting (IDW) onto a regular grid.
    Returns (Xg, Yg, Zg) for surface plotting; the scatter overlay shows true values.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)

    xi = np.linspace(x.min(), x.max(), grid_size)
    yi = np.linspace(y.min(), y.max(), grid_size)
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


def plot_activity_landscape_plotly(
    generation_id: int,
    method: Literal["pca", "tsne"] = "pca",
    mode: Literal["scatter", "surface"] = "scatter",
    grid_size: int = 60,
    out_path: Path | str = "outputs/activity_landscape.html",
) -> Path:
    """
    3D Plotly landscape: X/Y from PCA or t-SNE diversity, Z = activity score.
    'scatter' shows raw points; 'surface' adds an IDW-interpolated topography.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        df = pd.read_sql_query(
            """
            SELECT
              plasmid_variant_index,
              activity_score,
              pca_x, pca_y,
              tsne_x, tsne_y,
              protein_mutations
            FROM mv_activity_landscape
            WHERE generation_id = %s
              AND activity_score IS NOT NULL
            """,
            conn,
            params=(generation_id,),
        )

    if df.empty:
        raise RuntimeError(
            "No rows found in mv_activity_landscape. "
            "Have you computed embeddings and refreshed the MV?"
        )

    xcol, ycol = ("pca_x", "pca_y") if method == "pca" else ("tsne_x", "tsne_y")
    df = df.dropna(subset=[xcol, ycol, "activity_score"])

    if df.empty:
        raise RuntimeError(
            f"No usable rows after dropping NA for {method}. "
            "Do you have pca/tsne metrics stored?"
        )

    x = df[xcol].to_numpy()
    y = df[ycol].to_numpy()
    z = df["activity_score"].to_numpy()

    fig = go.Figure()

    # Surface layer (interpolated)
    if mode == "surface":
        Xg, Yg, Zg = _grid_interpolate_idw(x, y, z, grid_size=grid_size, power=2.0)
        fig.add_trace(
            go.Surface(
                x=Xg,
                y=Yg,
                z=Zg,
                opacity=0.75,
                showscale=True,
                hovertemplate=(
                    f"{method.upper()}1: %{{x:.3f}}<br>"
                    f"{method.upper()}2: %{{y:.3f}}<br>"
                    "Activity: %{z:.3f}<extra></extra>"
                ),
                name="Interpolated surface",
            )
        )

    # Point overlay
    fig.add_trace(
        go.Scatter3d(
            x=x,
            y=y,
            z=z,
            mode="markers",
            text=df["plasmid_variant_index"],
            customdata=df["protein_mutations"],
            marker=dict(size=4),
            hovertemplate=(
                "Variant: %{text}<br>"
                f"{xcol}: %{{x:.3f}}<br>"
                f"{ycol}: %{{y:.3f}}<br>"
                "Activity: %{z:.3f}<br>"
                "Protein muts: %{customdata}<extra></extra>"
            ),
            name="Variants",
        )
    )

    title_mode = "Surface + points" if mode == "surface" else "Points"
    fig.update_layout(
        title=f"3D Activity Landscape (Gen {generation_id}, {method.upper()}, {title_mode})",
        scene=dict(
            xaxis_title=f"{method.upper()} dim 1",
            yaxis_title=f"{method.upper()} dim 2",
            zaxis_title="Activity Score",
        ),
        margin=dict(l=0, r=0, t=60, b=0),
    )

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(
        description="3D Activity Landscape: X/Y = PCA or t-SNE (diversity), Z = activity_score"
    )
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--method", choices=["pca", "tsne"], default="pca")
    ap.add_argument(
        "--mode",
        choices=["scatter", "surface"],
        default="scatter",
        help="scatter = points only; surface = interpolated topography + points overlay",
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