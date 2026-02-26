from __future__ import annotations

from pathlib import Path
from typing import Union

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle


def plot_activity_distribution(df_dist: pd.DataFrame, out_path: Union[str, Path]) -> None:
    if df_dist is None or df_dist.empty:
        raise ValueError("df_dist is empty; nothing to plot")

    out_path = Path(out_path) # It needs to be a path object to get the parent directory (next line)
    out_path.parent.mkdir(parents=True, exist_ok=True) 

    gen_col = next((c for c in ("generation_number", "generation_id", "generation", "gen") if c in df_dist.columns), None)
    score_col = next((c for c in ("activity_score", "value", "score") if c in df_dist.columns), None)
    if gen_col is None or score_col is None:
        raise ValueError(f"Expected generation + score columns, got: {list(df_dist.columns)}")

    d = df_dist[[gen_col, score_col]].copy() #Only relevant colummns, and copy to avoid modifying the original dataframe
    d[score_col] = pd.to_numeric(d[score_col], errors="coerce")
    d = d.dropna(subset=[gen_col, score_col])

    # Keep generation order explicit so plot positions and labels stay aligned.
    generations = sorted(d[gen_col].unique().tolist()) #unique generations in sorted order
    data = [d.loc[d[gen_col] == g, score_col].to_numpy() for g in generations]
    # Use sequential positions to keep spacing/layout consistent with the reference style.
    xs = np.arange(1, len(generations) + 1)

    fig, ax = plt.subplots(figsize=(10, 7))

    parts = ax.violinplot(
        data,
        positions=xs,
        widths=0.75,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )

    for body in parts["bodies"]:
        body.set_alpha(0.35)
        body.set_edgecolor("none")

    # Summary stats are overlaid to make central tendency and spread easy to compare.
    mins = np.array([np.min(v) for v in data]) #min value for each generation
    maxs = np.array([np.max(v) for v in data]) #max value for each generation
    means = np.array([np.mean(v) for v in data]) #mean value for each generation
    medians = np.array([np.median(v) for v in data]) #median value for each generation

    ax.vlines(xs, mins, maxs, linewidth=2.5)
    cap = 0.10
    ax.hlines(mins, xs - cap, xs + cap, linewidth=2.5)
    ax.hlines(maxs, xs - cap, xs + cap, linewidth=2.5)

    ax.hlines(medians, xs - 0.12, xs + 0.12, linewidth=3.5)
    ax.hlines(means, xs - 0.08, xs + 0.08, linewidth=2.0)

    ax.set_title("Activity Score Distribution by Generation", fontsize=18)
    ax.set_xlabel("Generation", fontsize=14)
    ax.set_ylabel("Activity Score", fontsize=14)
    ax.axhline(1.0, color="red", linewidth=1.4, alpha=0.8, linestyle="--", label="WT control baseline = 1.0")

    y_min = float(np.min(mins)) #min value across all generations
    y_max = float(np.max(maxs)) #max value across all generations
    # Add adaptive padding so whiskers and baseline are not clipped.
    pad = max(0.5, 0.08 * (y_max - y_min)) #bìvisibility of all data points and baseline
    ax.set_ylim(y_min - pad, y_max + pad) 

    ax.set_xticks(xs)
    ax.set_xticklabels([str(g) for g in generations], fontsize=12)
    ax.tick_params(axis="y", labelsize=12)

    ax.grid(True, axis="both", linewidth=1.6, alpha=0.6)
    ax.legend(frameon=False, fontsize=11, loc="upper right")

    for spine in ax.spines.values(): 
        spine.set_color("0.8")
        spine.set_linewidth(1.5)

    fig.add_artist(
        Rectangle((0, 0), 1, 1, transform=fig.transFigure,
                  fill=False, edgecolor="black", linewidth=3.0)
    )

    fig.tight_layout(pad=2.0)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
