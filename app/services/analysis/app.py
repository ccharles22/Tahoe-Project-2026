from __future__ import annotations

from pathlib import Path
from flask import Flask, render_template

from .database import get_conn
from .queries import (
    fetch_top10, fetch_distribution,
    fetch_lineage_nodes, fetch_lineage_edges,
)

from .plots.top10 import plot_top10_table
from .plots.distribution import plot_activity_distribution
from .plots.lineage import plot_layered_lineage

app = Flask(__name__)

PLOTS_DIR = Path("static/plots")
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/top10/<int:experiment_id>")
def top10(experiment_id: int):
    with get_conn() as conn:
        df = fetch_top10(conn, experiment_id)

    out_path = PLOTS_DIR / f"top10_exp{experiment_id}.png"
    plot_top10_table(df, out_path)

    return render_template(
        "analysis/top10.html",
        experiment_id=experiment_id,
        top10_png=f"plots/top10_exp{experiment_id}.png",
    )


@app.route("/distribution/<int:experiment_id>")
def distribution(experiment_id: int):
    with get_conn() as conn:
        df = fetch_distribution(conn, experiment_id)

    out_path = PLOTS_DIR / f"dist_exp{experiment_id}.png"
    plot_activity_distribution(df, out_path)

    return render_template(
        "analysis/distribution.html",
        experiment_id=experiment_id,
        dist_png=f"plots/dist_exp{experiment_id}.png",
    )


@app.route("/lineage/<int:experiment_id>")
def lineage(experiment_id: int):
    with get_conn() as conn:
        nodes = fetch_lineage_nodes(conn, experiment_id)
        edges = fetch_lineage_edges(conn, experiment_id)

    out_path = PLOTS_DIR / f"lineage_exp{experiment_id}.png"
    plot_layered_lineage(nodes, edges, out_path)

    return render_template(
        "analysis/lineage.html",
        experiment_id=experiment_id,
        lineage_png=f"plots/lineage_exp{experiment_id}.png",
    )

