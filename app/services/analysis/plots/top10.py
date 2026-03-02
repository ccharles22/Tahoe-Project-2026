"""Matplotlib renderer for the Top 10 ranked variant table."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle


def plot_top10_table(df_top10: pd.DataFrame, out_path: Union[str, Path]) -> None:
    """Render the Top 10 ranking table image for one experiment."""
    if df_top10 is None or df_top10.empty:
        raise ValueError("df_top10 is empty; nothing to plot")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Prefer a stable column order; gracefully fall back if schema/query changes.
    preferred = ["generation_number", "plasmid_variant_index", "activity_score", "total_mutations"]
    cols = [c for c in preferred if c in df_top10.columns]
    if not cols:
        cols = list(df_top10.columns)

    t = df_top10[cols].copy()

    # Short labels keep the rendered table compact and readable.
    rename = {
        "generation_number": "Gen",
        "plasmid_variant_index": "Plasmid Variant Index",
        "activity_score": "Activity score",
        "total_mutations": "Total Mutations vs WT",
    }
    t = t.rename(columns={c: rename.get(c, c) for c in t.columns})

    # Normalize numeric display to fixed precision for clean alignment.
    for c in t.columns:
        if "score" in c.lower():
            t[c] = pd.to_numeric(t[c], errors="coerce").map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
        elif t[c].dtype.kind in "fc":
            t[c] = pd.to_numeric(t[c], errors="coerce").map(lambda x: "" if pd.isna(x) else f"{x:.3f}")

    # Scale figure height with row count to avoid clipping.
    nrows = len(t) + 1
    fig_h = max(2.8, 0.50 * nrows)
    fig, ax = plt.subplots(figsize=(9.5, fig_h))
    ax.axis("off")

    table = ax.table(
        cellText=t.values.tolist(),
        colLabels=t.columns.tolist(),
        cellLoc="center",
        colLoc="center",
        loc="center",
    )

    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.35)

    # Header emphasis + zebra striping improve scanability.
    for (r, c), cell in table.get_celld().items():
        cell.set_linewidth(1.0)
        if r == 0:
            cell.set_facecolor("0.90")
            cell.set_text_props(weight="bold")
            cell.set_height(cell.get_height() * 1.15)
        else:
            if r % 2 == 0:
                cell.set_facecolor("0.97")

    ax.set_title("Top 10 Performers", fontsize=16, pad=16)

    fig.add_artist(
        Rectangle((0, 0), 1, 1, transform=fig.transFigure,
                  fill=False, edgecolor="black", linewidth=3.0)
    )

    fig.tight_layout(pad=1.6)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
