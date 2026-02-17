from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Literal, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

LabelMode = Literal["none", "top10", "all"]
LayoutMode = Literal["stack", "pack"]
SubgraphMode = Literal["all", "top10_ancestors"]


@dataclass(frozen=True)
class PlotConfig:
    figsize: tuple[float, float] = (14, 6)
    dpi: int = 200

    # node/edge styling
    node_size: float = 35.0
    top10_size_boost: float = 85.0
    non_top_alpha: float = 0.25
    top_alpha: float = 1.0

    edge_alpha: float = 0.12
    edge_alpha_top: float = 0.45
    edge_lw: float = 0.9
    node_edgecolor: str = "black"
    lw_top10: float = 2.0
    lw_other: float = 0.0  # no outlines for non-top by default (cleaner)

    # labeling
    label_mode: LabelMode = "top10"  # "none" | "top10" | "all"
    label_fontsize: int = 8
    label_offset: float = 0.18
    max_labels_per_generation: int | None = None  # safety valve for "all"

    # layout
    layout_mode: LayoutMode = "pack"  # "stack" keeps original behavior
    pack_generation_height: float = 6.0   # pack height per generation band
    generation_band_gap: float = 0.7      # vertical space between generation bands

    # readability controls
    subgraph_mode: SubgraphMode = "top10_ancestors"  # default: show top10 + ancestors
    parent_sorted_layout: bool = True                # reduce edge crossings

    title: str = "Variant Lineage"


def _require_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required column(s): {sorted(missing)}")


def _filter_subgraph(
    nodes: pd.DataFrame, edges: pd.DataFrame | None, mode: SubgraphMode
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """
    Reduce clutter by keeping only Top10 nodes and their ancestors.
    """
    if mode == "all" or edges is None or edges.empty or "is_top10" not in nodes.columns:
        return nodes, edges

    top_ids = set(
        pd.to_numeric(nodes["variant_id"], errors="coerce")
        .where(pd.to_numeric(nodes["is_top10"], errors="coerce").fillna(0).astype(int) == 1)
        .dropna()
        .astype(int)
        .tolist()
    )
    if not top_ids:
        return nodes, edges

    edges2 = edges.copy()
    edges2["child_id"] = pd.to_numeric(edges2["child_id"], errors="coerce")
    edges2["parent_id"] = pd.to_numeric(edges2["parent_id"], errors="coerce")
    edges2 = edges2.dropna(subset=["child_id", "parent_id"])
    edges2["child_id"] = edges2["child_id"].astype(int)
    edges2["parent_id"] = edges2["parent_id"].astype(int)

    parent_map = dict(zip(edges2["child_id"], edges2["parent_id"]))

    keep: set[int] = set(top_ids)
    stack = list(top_ids)
    while stack:
        cid = stack.pop()
        pid = parent_map.get(cid)
        if pid is not None and pid not in keep:
            keep.add(pid)
            stack.append(pid)

    nodes2 = nodes.copy()
    nodes2["variant_id_int"] = pd.to_numeric(nodes2["variant_id"], errors="coerce").astype("Int64")
    nodes_f = nodes2[nodes2["variant_id_int"].isin(list(keep))].drop(columns=["variant_id_int"])

    edges_f = edges2[edges2["child_id"].isin(keep) & edges2["parent_id"].isin(keep)].copy()
    return nodes_f, edges_f


def _layout_nodes(nodes: pd.DataFrame, cfg: PlotConfig) -> pd.DataFrame:
    """
    Assign (x, y) coordinates.
    x = generation_number
    y = position within generation, optionally packed to fixed height per generation
    """
    _require_columns(nodes, {"variant_id", "generation_number"}, "nodes")
    df = nodes.copy()

    df["generation_number"] = pd.to_numeric(df["generation_number"], errors="coerce")
    if df["generation_number"].isna().all():
        raise ValueError("nodes['generation_number'] could not be parsed as numeric")

    # Sort preference:
    sort_cols: list[str] = ["generation_number"]
    ascending: list[bool] = [True]

    has_activity = "activity_score" in df.columns and df["activity_score"].notna().any()
    if has_activity:
        sort_cols.append("activity_score")
        ascending.append(False)
    elif "plasmid_variant_index" in df.columns:
        sort_cols.append("plasmid_variant_index")
        ascending.append(True)

    df = df.sort_values(sort_cols, ascending=ascending, kind="mergesort")

    df["x"] = df["generation_number"].astype(int)

    rank = df.groupby("generation_number", sort=False).cumcount()
    n_in_gen = df.groupby("generation_number", sort=False)["variant_id"].transform("size")
    base = (n_in_gen - 1 - rank).astype(float)

    if cfg.layout_mode == "stack":
        df["y"] = base
        return df

    denom = (n_in_gen - 1).astype(float).where((n_in_gen - 1) > 0, 1.0)
    scaled = (base / denom) * cfg.pack_generation_height

    gens = pd.Series(df["generation_number"].unique()).sort_values().to_list()
    gen_to_offset = {g: i * (cfg.pack_generation_height + cfg.generation_band_gap) for i, g in enumerate(gens)}
    offsets = df["generation_number"].map(gen_to_offset).astype(float)

    df["y"] = scaled + offsets
    return df


def _order_by_parent(df: pd.DataFrame, edges: pd.DataFrame | None) -> pd.DataFrame:
    """
    Reorder nodes within each generation so children cluster near their parents.
    This reduces crossings and makes families visually coherent.
    """
    if edges is None or edges.empty:
        return df

    d = df.copy()
    d["_vid"] = pd.to_numeric(d["variant_id"], errors="coerce")
    d = d.dropna(subset=["_vid"])
    d["_vid"] = d["_vid"].astype(int)

    e = edges.copy()
    e["child_id"] = pd.to_numeric(e["child_id"], errors="coerce")
    e["parent_id"] = pd.to_numeric(e["parent_id"], errors="coerce")
    e = e.dropna(subset=["child_id", "parent_id"])
    e["child_id"] = e["child_id"].astype(int)
    e["parent_id"] = e["parent_id"].astype(int)

    parent = dict(zip(e["child_id"], e["parent_id"]))

    # Initial order within generation based on current df order
    d["_ord"] = d.groupby("generation_number", sort=False).cumcount().astype(float)

    # Two passes is usually enough
    for _ in range(2):
        ord_map = dict(zip(d["_vid"], d["_ord"]))
        d["_pord"] = d["_vid"].map(lambda vid: ord_map.get(parent.get(vid, -1), np.nan))
        d["_key"] = d["_pord"].fillna(d["_ord"])
        d = d.sort_values(["generation_number", "_key"], kind="mergesort")
        d["_ord"] = d.groupby("generation_number", sort=False).cumcount().astype(float)

    d = d.drop(columns=["_ord", "_pord", "_key", "_vid"])
    return d


def _build_pos(df: pd.DataFrame) -> Mapping[int, tuple[float, float]]:
    vid = pd.to_numeric(df["variant_id"], errors="coerce")
    valid = vid.notna()
    if not valid.any():
        raise ValueError("nodes['variant_id'] could not be parsed as numeric IDs")

    tmp = df.loc[valid, ["x", "y"]].copy()
    tmp.index = vid.loc[valid].astype(int)
    tmp = tmp[~tmp.index.duplicated(keep="first")]

    return {int(k): (float(v["x"]), float(v["y"])) for k, v in tmp.to_dict("index").items()}


def _node_label(row: pd.Series) -> str:
    gen = int(row["generation_number"])
    if "plasmid_variant_index" in row and pd.notna(row["plasmid_variant_index"]):
        return f"G{gen}:{int(row['plasmid_variant_index'])}"
    if "variant_id" in row and pd.notna(row["variant_id"]):
        vid = pd.to_numeric(row["variant_id"], errors="coerce")
        if pd.notna(vid):
            return f"G{gen} v{int(vid)}"
    return f"G{gen}"


def plot_layered_lineage(
    nodes: pd.DataFrame,
    edges: pd.DataFrame | None,
    out_path: str | Path | PathLike[str],
    *,
    config: PlotConfig = PlotConfig(),
) -> None:
    """
    Better-looking lineage plot:
      - defaults to Top10+ancestors to avoid hairball
      - reduces crossings by ordering children near parents
      - fades non-top nodes and edges
      - labels Top10 only by default
    """
    if nodes is None or nodes.empty:
        raise ValueError("nodes is empty; nothing to plot")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    nodes_f, edges_f = _filter_subgraph(nodes, edges, config.subgraph_mode)

    df = _layout_nodes(nodes_f, config)
    if config.parent_sorted_layout:
        df = _order_by_parent(df, edges_f)

    pos = _build_pos(df)

    fig, ax = plt.subplots(figsize=config.figsize)

    # --- edge drawing (behind nodes) ---
    if edges_f is not None and not edges_f.empty:
        _require_columns(edges_f, {"parent_id", "child_id"}, "edges")

        parent_ids = pd.to_numeric(edges_f["parent_id"], errors="coerce").astype("Int64")
        child_ids = pd.to_numeric(edges_f["child_id"], errors="coerce").astype("Int64")

        edge_alpha = config.edge_alpha_top if config.subgraph_mode != "all" else config.edge_alpha

        for p_id, c_id in zip(parent_ids, child_ids):
            if pd.isna(p_id) or pd.isna(c_id):
                continue
            p = pos.get(int(p_id))
            c = pos.get(int(c_id))
            if p is None or c is None:
                continue
            ax.plot(
                [p[0], c[0]],
                [p[1], c[1]],
                linewidth=config.edge_lw,
                alpha=edge_alpha,
                zorder=1,
            )

    # --- node coloring ---
    is_top = (
        pd.to_numeric(df.get("is_top10", 0), errors="coerce")
        .fillna(0)
        .astype(int)
        .to_numpy()
    )
    mask_top = is_top == 1

    cvals = None
    norm = None
    if "activity_score" in df.columns and df["activity_score"].notna().any():
        cvals = pd.to_numeric(df["activity_score"], errors="coerce").to_numpy()
        finite = np.isfinite(cvals)
        if finite.any():
            norm = Normalize(vmin=float(np.nanmin(cvals)), vmax=float(np.nanmax(cvals)))

    # --- non-top nodes first (faint) ---
    ax.scatter(
        df.loc[~mask_top, "x"],
        df.loc[~mask_top, "y"],
        s=config.node_size,
        c=(cvals[~mask_top] if cvals is not None else None),
        norm=norm,
        alpha=config.non_top_alpha,
        linewidths=0.0 if config.lw_other == 0.0 else config.lw_other,
        edgecolors="none" if config.lw_other == 0.0 else config.node_edgecolor,
        zorder=2,
    )

    # --- top nodes on top (prominent) ---
    sc = ax.scatter(
        df.loc[mask_top, "x"],
        df.loc[mask_top, "y"],
        s=config.node_size + config.top10_size_boost,
        c=(cvals[mask_top] if cvals is not None else None),
        norm=norm,
        alpha=config.top_alpha,
        linewidths=config.lw_top10,
        edgecolors=config.node_edgecolor,
        zorder=3,
    )

    # --- labels ---
    if config.label_mode != "none":
        if config.label_mode == "top10":
            df_for_labels = df.loc[mask_top]
        elif config.label_mode == "all" and config.max_labels_per_generation is not None:
            df_for_labels = (
                df.assign(_rank_in_gen=df.groupby("generation_number", sort=False).cumcount())
                .loc[lambda d: d["_rank_in_gen"] < config.max_labels_per_generation]
                .drop(columns="_rank_in_gen")
            )
        else:
            df_for_labels = df

        for _, row in df_for_labels.iterrows():
            top = int(pd.to_numeric(row.get("is_top10", 0), errors="coerce") or 0) == 1
            base = _node_label(row)
            label = f"★ {base}" if top else base

            ax.text(
                float(row["x"]),
                float(row["y"]) + config.label_offset,
                label,
                ha="center",
                va="bottom",
                fontsize=config.label_fontsize,
                zorder=4,
            )

    # --- axes styling ---
    ax.set_title(config.title, fontsize=16)
    ax.set_xlabel("Generation", fontsize=12)
    ax.set_ylabel("")
    ax.set_xticks(sorted(df["x"].unique().tolist()))
    ax.set_yticks([])
    ax.grid(True, axis="x", linewidth=1.2, alpha=0.35)

    if cvals is not None and norm is not None:
        fig.colorbar(sc, ax=ax, label="Activity score")

    fig.add_artist(
        Rectangle(
            (0, 0),
            1,
            1,
            transform=fig.transFigure,
            fill=False,
            edgecolor="black",
            linewidth=2.2,
        )
    )

    fig.tight_layout(pad=1.6)
    fig.savefig(out_path, dpi=config.dpi)
    plt.close(fig)
