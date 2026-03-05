"""Static Matplotlib surface preview for activity embedding space."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

from app.services.analysis.bonus.visualisations.plot_activity_landscape import (
    _load_experiment_landscape_frame,
)


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
    """Render an IDW-interpolated surface with a scatter overlay as a static PNG.

    Args:
        generation_id: Any generation in the target experiment.
        method: Dimensionality reduction method (``"pca"`` or ``"tsne"``).
        grid_size: Surface interpolation grid resolution.
        out_path: Destination PNG file path.

    Returns:
        Path to the written PNG file.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    experiment_id, df = _load_experiment_landscape_frame(generation_id, method)

    x = df["x"].to_numpy()
    y = df["y"].to_numpy()
    z = df["activity_score"].to_numpy()

    Xg, Yg, Zg = grid_interpolate_idw(x, y, z, grid_size=grid_size)

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection="3d")
    ax.plot_surface(Xg, Yg, Zg, rstride=1, cstride=1, linewidth=0, antialiased=True, alpha=0.85)
    ax.scatter(x, y, z, s=10)

    ax.set_title(f"Activity Landscape Surface (Experiment {experiment_id}, {method.upper()})")
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
