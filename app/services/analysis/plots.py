"""Legacy plotting helper kept for compatibility with earlier imports."""

from __future__ import annotations
import os
import pandas as pd
import matplotlib.pyplot as plt

def plot_activity_distribution(df_dist: pd.DataFrame, outpath: str) -> str:
    """Render the legacy boxplot preview from generation/activity-score data."""
    if df_dist.empty:
        raise ValueError("No distribution data to plot (df_dist is empty).")

    groups = []
    labels = []
    for gen, gdf in df_dist.groupby("generation_number"):
        vals = gdf["activity_score"].dropna().values
        if len(vals) == 0:
            continue
        groups.append(vals)
        labels.append(str(gen))

    if not groups:
        raise ValueError("No non-null activity scores found for plotting.")

    plt.figure()
    plt.boxplot(groups, labels=labels, showfliers=False)
    plt.xlabel("Generation")
    plt.ylabel("Activity Score")
    plt.title("Activity Score Distribution per Generation")

    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=200)
    plt.close()
    return outpath
