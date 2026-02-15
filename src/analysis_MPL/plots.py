from __future__ import annotations

from pathlib import Path
from typing import Union

import matplotlib
matplotlib.use("Agg")  # must be before pyplot import

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle


def plot_top10_table(df_top10: pd.DataFrame, out_path: Union[str, Path]) -> None:
    """
    Render the Top-10 performers table to a PNG image.
    Expects columns like:
      generation_number, plasmid_variant_index, activity_score, protein_mutations
    (It will still work if a subset exists.)
    """
    if df_top10 is None or df_top10.empty:
        raise ValueError("df_top10 is empty; nothing to plot")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Choose / order columns if present
    preferred = ["generation_number", "plasmid_variant_index", "activity_score", "protein_mutations"]
    cols = [c for c in preferred if c in df_top10.columns]
    if not cols:
        cols = list(df_top10.columns)

    t = df_top10[cols].copy()

    # Friendly column names
    rename = {
        "generation_number": "Gen",
        "plasmid_variant_index": "Variant",
        "activity_score": "Activity score",
        "protein_mutations": "Protein muts",
    }
    t = t.rename(columns={c: rename.get(c, c) for c in t.columns})

    # Format numbers nicely
    for c in t.columns:
        if "score" in c.lower():
            t[c] = pd.to_numeric(t[c], errors="coerce").map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
        elif t[c].dtype.kind in "fc":
            t[c] = pd.to_numeric(t[c], errors="coerce").map(lambda x: "" if pd.isna(x) else f"{x:.3f}")

    # Build figure
    nrows = len(t) + 1  # + header
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

    # Base styling
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.35)

    # Header shading + zebra stripes + line widths
    for (r, c), cell in table.get_celld().items():
        cell.set_linewidth(1.0)
        if r == 0:
            cell.set_facecolor("0.90")  # light grey header
            cell.set_text_props(weight="bold")
            cell.set_height(cell.get_height() * 1.15)
        else:
            if r % 2 == 0:
                cell.set_facecolor("0.97")  # subtle alternating row shading

    ax.set_title("Top 10 Performers", fontsize=16, pad=16)

    # Thick black border around the whole figure (matches your report plot border)
    fig.add_artist(
        Rectangle(
            (0, 0), 1, 1,
            transform=fig.transFigure,
            fill=False,
            edgecolor="black",
            linewidth=3.0,
        )
    )

    fig.tight_layout(pad=1.6)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_activity_distribution(df_dist: pd.DataFrame, out_path: Union[str, Path]) -> None:
    # --- validate + prep ---
    if df_dist is None or df_dist.empty:
        raise ValueError("df_dist is empty; nothing to plot")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    gen_col = next(
        (c for c in ("generation_number", "generation_id", "generation", "gen") if c in df_dist.columns),
        None,
    )
    score_col = next(
        (c for c in ("activity_score", "value", "score") if c in df_dist.columns),
        None,
    )
    if gen_col is None or score_col is None:
        raise ValueError(f"Expected generation + score columns, got: {list(df_dist.columns)}")

    d = df_dist[[gen_col, score_col]].copy()
    d[score_col] = pd.to_numeric(d[score_col], errors="coerce")
    d = d.dropna(subset=[gen_col, score_col])

    generations = sorted(d[gen_col].unique().tolist())
    data = [d.loc[d[gen_col] == g, score_col].to_numpy() for g in generations]

    xs = np.arange(1, len(generations) + 1)

    # --- figure/axes ---
    fig, ax = plt.subplots(figsize=(10, 7))

    # Violin plot (no built-in extrema/means/medians; we'll draw those manually)
    parts = ax.violinplot(
        data,
        positions=xs,
        widths=0.75,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )

    # Style violins to match the example (soft fill, no heavy edge)
    for body in parts["bodies"]:
        body.set_alpha(0.35)
        body.set_edgecolor("none")

    # Summary stats
    mins = np.array([np.min(v) for v in data])
    maxs = np.array([np.max(v) for v in data])
    means = np.array([np.mean(v) for v in data])
    medians = np.array([np.median(v) for v in data])

    # Whiskers (min/max) with caps
    ax.vlines(xs, mins, maxs, linewidth=2.5)
    cap = 0.10
    ax.hlines(mins, xs - cap, xs + cap, linewidth=2.5)
    ax.hlines(maxs, xs - cap, xs + cap, linewidth=2.5)

    # Inner bars: median (thicker), mean (thinner) – like the example “double bar”
    ax.hlines(medians, xs - 0.12, xs + 0.12, linewidth=3.5)
    ax.hlines(means, xs - 0.08, xs + 0.08, linewidth=2.0)

    # Labels/title exactly like the example
    ax.set_title("Activity Score Distribution by Generation", fontsize=18)
    ax.set_xlabel("Generation", fontsize=14)
    ax.set_ylabel("Activity Score", fontsize=14)

    ax.set_xticks(xs)
    ax.set_xticklabels([str(g) for g in generations], fontsize=12)
    ax.tick_params(axis="y", labelsize=12)

    # Gridlines on BOTH axes (light grey)
    ax.grid(True, axis="both", linewidth=1.6, alpha=0.6)

    # Light grey axis spines
    for spine in ax.spines.values():
        spine.set_color("0.8")
        spine.set_linewidth(1.5)

    # Thick black border around the whole figure (like the screenshot)
    fig.add_artist(
        Rectangle(
            (0, 0), 1, 1,
            transform=fig.transFigure,
            fill=False,
            edgecolor="black",
            linewidth=3.0,
        )
    )

    fig.tight_layout(pad=2.0)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
