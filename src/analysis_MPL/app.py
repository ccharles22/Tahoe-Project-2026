from __future__ import annotations

from pathlib import Path
import time
from flask import Flask, render_template, request

from src.analysis_MPL.database import get_conn
from src.analysis_MPL.queries import (
    fetch_top10, fetch_distribution,
    fetch_lineage_nodes, fetch_lineage_edges,
    fetch_protein_similarity_nodes, fetch_protein_mutations,
)

from src.analysis_MPL.plots.top10 import plot_top10_table
from src.analysis_MPL.plots.distribution import plot_activity_distribution
from src.analysis_MPL.plots.lineage import plot_layered_lineage
from src.analysis_MPL.plots.protein_similarity_network import (
    ProteinNetConfig,
    plot_protein_similarity_network,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = ROOT_DIR / "app"

app = Flask(
    __name__,
    template_folder=str(APP_DIR / "templates"),
    static_folder=str(APP_DIR / "static"),
)

PLOTS_DIR = Path(app.static_folder) / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/top10/<int:experiment_id>")
def top10(experiment_id: int):
    with get_conn() as conn:
        df = fetch_top10(conn, experiment_id)

    out_path = PLOTS_DIR / f"top10_exp{experiment_id}.png"
    plot_top10_table(df, out_path)

    return render_template(
        "top10.html",
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
        "distribution.html",
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
        "lineage.html",
        experiment_id=experiment_id,
        lineage_png=f"plots/lineage_exp{experiment_id}.png",
    )


@app.route("/protein_similarity/<int:experiment_id>")
def protein_similarity(experiment_id: int):
    mode = request.args.get("mode", "identity").strip().lower()
    if mode not in {"identity", "cooccurrence"}:
        mode = "identity"

    preset = request.args.get("preset", "").strip().lower()
    identity_threshold = request.args.get("identity_threshold", "0.95")
    min_shared = request.args.get("min_shared", "1")
    jaccard_threshold = request.args.get("jaccard_threshold", "")
    max_nodes = request.args.get("max_nodes", "40")

    allowed_max_nodes = {20, 30, 40, 50, 80, 120, 250}

    try:
        identity_threshold_val = float(identity_threshold)
    except ValueError:
        identity_threshold_val = 0.95

    try:
        min_shared_val = max(1, int(min_shared))
    except ValueError:
        min_shared_val = 1

    jaccard_threshold_val = None
    if jaccard_threshold.strip():
        try:
            jaccard_threshold_val = float(jaccard_threshold)
        except ValueError:
            jaccard_threshold_val = None

    try:
        max_nodes_val = int(max_nodes)
    except ValueError:
        max_nodes_val = 40
    if max_nodes_val not in allowed_max_nodes:
        max_nodes_val = 40

    if preset in {"sparse", "medium", "dense"}:
        if mode == "identity":
            identity_threshold_val = {"sparse": 0.98, "medium": 0.95, "dense": 0.90}[preset]
        else:
            preset_map = {
                "sparse": (4, 0.20),
                "medium": (2, 0.10),
                "dense": (1, None),
            }
            min_shared_val, jaccard_threshold_val = preset_map[preset]

    with get_conn() as conn:
        nodes = fetch_protein_similarity_nodes(conn, experiment_id)
        mutations = fetch_protein_mutations(conn, experiment_id) if mode == "cooccurrence" else None

    suffix = f"{mode}_it{identity_threshold_val:.2f}_ms{min_shared_val}_n{max_nodes_val}"
    if jaccard_threshold_val is not None:
        suffix = f"{suffix}_jt{jaccard_threshold_val:.2f}"
    out_path = PLOTS_DIR / f"protein_exp{experiment_id}_{suffix}.png"

    if mode == "identity":
        title = f"Protein Similarity Network (Top {max_nodes_val} Variants by Activity)"
    else:
        title = f"Protein Co-Occurrence Network (Top {max_nodes_val} Variants by Activity)"
    config = ProteinNetConfig(
        title=title,
        identity_threshold=identity_threshold_val,
        cooccur_min_shared_mutations=min_shared_val,
        cooccur_jaccard_threshold=jaccard_threshold_val,
        top_n_by_activity=max_nodes_val,
        max_nodes_final=max_nodes_val,
    )

    plot_protein_similarity_network(
        nodes,
        out_path,
        mode=mode,
        mutations=mutations,
        config=config,
    )

    return render_template(
        "protein_similarity.html",
        experiment_id=experiment_id,
        protein_png=f"plots/protein_exp{experiment_id}_{suffix}.png",
        mode=mode,
        preset=preset,
        identity_threshold=identity_threshold_val,
        min_shared=min_shared_val,
        jaccard_threshold=jaccard_threshold_val if jaccard_threshold_val is not None else "",
        max_nodes=max_nodes_val,
        max_node_options=sorted(allowed_max_nodes),
        cache_buster=int(time.time()),
    )
