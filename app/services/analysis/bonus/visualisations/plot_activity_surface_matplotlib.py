"""Static Matplotlib surface preview for activity embedding space."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from app.services.analysis.bonus.database.postgres import get_connection


def grid_interpolate_idw(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    grid_size: int = 60,
    power: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate scattered points onto a grid via inverse-distance weighting."""
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


def plot_activity_surface_matplotlib(
    generation_id: int,
    method: Literal["pca", "tsne"] = "pca",
    grid_size: int = 60,
    out_path: Path | str = "outputs/activity_surface.png",
) -> Path:
    """IDW-interpolated surface + scatter overlay exported as a static PNG."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        x_metric = f"{method}_x"
        y_metric = f"{method}_y"
        df = pd.read_sql_query(
            """
            SELECT
              MAX(CASE WHEN m.metric_name = %s THEN m.value END) AS x,
              MAX(CASE WHEN m.metric_name = %s THEN m.value END) AS y,
              MAX(CASE WHEN m.metric_name = 'activity_score' THEN m.value END) AS activity_score
            FROM variants v
            LEFT JOIN metrics m
              ON m.variant_id = v.variant_id
             AND m.generation_id = v.generation_id
             AND m.metric_type = 'derived'
             AND m.metric_name IN (%s, %s, 'activity_score')
            WHERE v.generation_id = %s
            GROUP BY v.variant_id
            HAVING MAX(CASE WHEN m.metric_name = 'activity_score' THEN m.value END) IS NOT NULL
            """,
            conn,
            params=(x_metric, y_metric, x_metric, y_metric, generation_id),
        )

    xcol, ycol = ("x", "y")
    df = df.dropna(subset=[xcol, ycol, "activity_score"])
    if df.empty:
        raise RuntimeError("No data available for surface plot (missing coords or activity_score).")

    x = df[xcol].to_numpy()
    y = df[ycol].to_numpy()
    z = df["activity_score"].to_numpy()

    Xg, Yg, Zg = grid_interpolate_idw(x, y, z, grid_size=grid_size)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(Xg, Yg, Zg, rstride=1, cstride=1, linewidth=0, antialiased=True, alpha=0.85)
    ax.scatter(x, y, z, s=10)

    ax.set_title(f"Activity Landscape Surface (Gen {generation_id}, {method.upper()})")
    ax.set_xlabel(f"{method.upper()} dim 1")
    ax.set_ylabel(f"{method.upper()} dim 2")
    ax.set_zlabel("Activity Score")

    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def main():
    """CLI entrypoint for exporting a static activity-surface image."""
    ap = argparse.ArgumentParser(description="Static 3D surface export using Matplotlib mplot3d.")
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--method", choices=["pca", "tsne"], default="pca")
    ap.add_argument("--grid-size", type=int, default=60)
    ap.add_argument("--out", default="outputs/activity_surface.png")
    args = ap.parse_args()

    out = plot_activity_surface_matplotlib(
        generation_id=args.generation_id,
        method=args.method,
        grid_size=args.grid_size,
        out_path=args.out,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
