"""Matplotlib-based analysis plots (integrated from teammate's MPL branch).

Public API re-exported from sub-modules:

* ``plot_activity_distribution`` – violin/box distribution per generation.
* ``plot_top10_table``           – ranked table image of top-10 performers.
* ``plot_layered_lineage``       – layered lineage DAG with optional trendline.
* ``PlotConfig``                 – frozen dataclass tuning every aspect of the lineage plot.
"""
from .distribution import plot_activity_distribution
from .top10 import plot_top10_table
from .lineage import plot_layered_lineage, PlotConfig

__all__ = [
    "plot_activity_distribution",
    "plot_top10_table",
    "plot_layered_lineage",
    "PlotConfig",
]
