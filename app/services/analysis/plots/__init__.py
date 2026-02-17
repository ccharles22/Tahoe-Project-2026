"""Matplotlib-based analysis plots (integrated from teammate's MPL branch)."""
from .distribution import plot_activity_distribution
from .top10 import plot_top10_table
from .lineage import plot_layered_lineage, PlotConfig

__all__ = [
    "plot_activity_distribution",
    "plot_top10_table",
    "plot_layered_lineage",
    "PlotConfig",
]
