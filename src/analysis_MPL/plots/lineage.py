from __future__ import annotations

from pathlib import Path
from typing import Union

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle


def plot_layered_lineage(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    out_path: Union[str, Path],
) -> None:
    """
    Layered lineage plot saved as PNG.
    Highlights Top-10 variants if `is_top10` column is present in `nodes`.
    """

    if nodes is None or nodes.empty:
        raise ValueError("nodes is empty; nothing to plot")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df = nodes.copy()

    # Sort within generation
    if "activity_score" in df.columns and df["activity_score"].notna().any():
        df = df.sort_values(["generation_number", "activity_score"], ascending=[True, False])
    else:
        df = df.sort_values(["generation_number", "plasmid_variant_index"], ascending=[True, True])

    # Assign positions (layered)
    df["x"] = df["generation_number"].astype(int)
    df["y"] = df.groupby("generation_number").cumcount()
    df["y"] = df.groupby("generation_number")["y"].transform(lambda s: s.max() - s)

    pos = df.set_index("variant_id")[["x", "y"]].to_dict("index")

    fig, ax = plt.subplots(figsize=(12, 7))

    # Draw edges
    if edges is not None and not edges.empty:
        for r in edges.itertuples(index=False):
            parent_id = getattr(r, "parent_id")
            child_id = getattr(r, "child_id")
            p = pos.get(int(parent_id))
            c = pos.get(int(child_id))
            if not p or not c:
                continue
            ax.plot([p["x"], c["x"]], [p["y"], c["y"]], linewidth=1.0, alpha=0.35)

    # Top10 handling (works even if column absent)
    is_top = (
        df["is_top10"].fillna(0).astype(int).to_numpy()
        if "is_top10" in df.columns
        else np.zeros(len(df), dtype=int)
    )

    # Node sizes (Top10 bigger)
    sizes = np.full(len(df), 55.0)
    sizes = sizes + is_top * 65.0  # bigger boost for top10

    # Edge outline: Top10 thicker outline
    linewidths = np.where(is_top == 1, 2.2, 0.8)

    # Color by activity if available
    cvals = None
    if "activity_score" in df.columns and df["activity_score"].notna().any():
        cvals = df["activity_score"].to_numpy()

    sc = ax.scatter(
        df["x"],
        df["y"],
        s=sizes,
        c=cvals,
        linewidths=linewidths,
        edgecolors="black",
    )

    # Labels (optional star for Top10)
    for r in df.itertuples(index=False):
        if hasattr(r, "is_top10") and int(getattr(r, "is_top10") or 0) == 1:
            label = f"★ G{int(r.generation_number)}:{int(r.plasmid_variant_index)}"
            ax.text(r.x, r.y + 0.15, label, ha="center", va="bottom", fontsize=8)

    ax.set_title("Variant Lineage (Layered by Generation)", fontsize=18)
    ax.set_xlabel("Generation", fontsize=14)
    ax.set_ylabel("")
    ax.set_xticks(sorted(df["x"].unique().tolist()))
    ax.set_yticks([])
    ax.grid(True, axis="x", linewidth=1.4, alpha=0.6)

    if cvals is not None:
        plt.colorbar(sc, ax=ax, label="Activity score")

    fig.add_artist(
        Rectangle(
            (0, 0),
            1,
            1,
            transform=fig.transFigure,
            fill=False,
            edgecolor="black",
            linewidth=3.0,
        )
    )

    fig.tight_layout(pad=2.0)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
