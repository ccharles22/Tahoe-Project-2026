"""Matplotlib renderer for the experiment-local lineage visualisation."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Hashable, Literal, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

try:
    from scipy.stats import linregress
except ImportError:  # pragma: no cover - optional runtime dependency.
    linregress = None

LabelMode = Literal["none", "topk", "all"]
LayoutMode = Literal["stack", "pack"]
YMode = Literal["rank", "activity"]
SubgraphMode = Literal["all", "top10_ancestors"]
ColorMode = Literal["lineage", "mutations", "activity", "none"]
LabelIdSource = Literal["plasmid_variant_index", "variant_id"]


# -----------------------------
# Config
# -----------------------------
@dataclass(frozen=True)
class PlotConfig:
    """Frozen configuration for every visual aspect of the lineage plot.

    All fields have sensible defaults; override only what you need.
    Group summaries:

    * **layout** – controls y-axis mode, jitter, and packing.
    * **readability** – subgraph filtering, parent-sorted ordering.
    * **encoding** – colour mapping (lineage / mutations / activity).
    * **nodes / edges** – sizes, alphas, line-widths.
    * **labeling** – which nodes get text labels and how.
    * **highlighting** – emphasise top-k per generation + ancestors.
    * **presentation** – grid lines, borders, optional trendline.
    """

    figsize: tuple[float, float] = (14, 6)
    dpi: int = 220
    title: str = "Variant Lineage"

    # layout
    y_mode: YMode = "activity"              # Option A
    layout_mode: LayoutMode = "pack"        # used only if y_mode="rank"
    pack_generation_height: float = 5.0     # used only if y_mode="rank" & layout_mode="pack"
    x_jitter: float = 0.18                  # bigger jitter helps readability

    # readability controls
    subgraph_mode: SubgraphMode = "all"     # IMPORTANT: show all by default
    only_connected_nodes: bool = False
    parent_sorted_layout: bool = True       # cluster children near parents
    enforce_consecutive_generations: bool = True  # remove edges that skip rounds (cleaner)

    # encoding
    color_mode: ColorMode = "lineage"       # default: lineage (mutations often messy)
    cmap_continuous: str = "viridis"
    cmap_categorical: str = "tab20"

    # nodes
    node_size: float = 34.0
    top10_size_boost: float = 90.0
    non_top_alpha: float = 0.12
    top_alpha: float = 1.0
    lw_top10: float = 2.0
    lw_other: float = 0.0
    node_edgecolor: str = "black"

    # edges
    edge_alpha: float = 0.08
    edge_alpha_top: float = 0.65
    edge_lw: float = 1.0
    edge_lw_top_boost: float = 0.7
    edge_color: str = "0.75"

    # labeling
    label_mode: LabelMode = "topk"          # far cleaner than "top10"
    label_fontsize: int = 8
    label_top_k_per_generation: int = 1     # avoids label piles
    max_labels_per_generation: int | None = None
    label_offset_frac_of_yrange: float = 0.02
    label_offset_rank_units: float = 0.18
    label_id_source: LabelIdSource = "plasmid_variant_index"

    # highlighting
    highlight_top_k_per_generation: int = 1 # highlight best per gen + ancestors

    # presentation
    show_generation_grid: bool = True
    show_horizontal_grid: bool = True
    show_figure_border: bool = False
    show_top10_branch_trend: bool = False
    top10_branch_trend_min_points: int = 3


@dataclass(frozen=True)
class BranchTrendStats:
    """Summary statistics for a linear trend fitted to top-variant ancestor branches."""

    top_variant_ids: tuple[Hashable, ...]
    point_count: int
    trend_ready: bool
    r_value: float | None
    p_value: float | None
    x_line: tuple[float, float] | None
    y_line: tuple[float, float] | None


# -----------------------------
# utils
# -----------------------------
def _require_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    """Raise ``ValueError`` if *df* is missing any of the *required* columns."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required column(s): {sorted(missing)}")


def _coerce_id_series(s: pd.Series) -> pd.Series:
    """Convert IDs into stable hashable keys WITHOUT forcing numeric.

    - Preserves ints and strings.
    - Converts float whole-numbers (1.0) → ``Int64(1)``.
    - Leaves other floats as strings.
    """
    if pd.api.types.is_integer_dtype(s) or pd.api.types.is_string_dtype(s):
        return s

    if pd.api.types.is_float_dtype(s):
        out = s.copy()
        arr = out.to_numpy()
        mask = out.notna() & np.isfinite(arr)
        whole = mask & (np.floor(arr) == arr)
        out2 = out.astype("object")
        out2.loc[whole] = out.loc[whole].astype("Int64")
        out2.loc[mask & ~whole] = out.loc[mask & ~whole].astype(str)
        return out2

    return s.astype("object")


def _filter_edges_to_nodes(
    nodes: pd.DataFrame,
    edges: pd.DataFrame | None,
    *,
    node_id_col: str,
    parent_col: str,
    child_col: str,
) -> pd.DataFrame | None:
    """Drop edges that don't reference node IDs (prevents silent 'no lines')."""
    if edges is None or edges.empty:
        return edges

    _require_columns(nodes, {node_id_col}, "nodes")
    _require_columns(edges, {parent_col, child_col}, "edges")

    node_ids = set(_coerce_id_series(nodes[node_id_col]).dropna().tolist())

    e = edges.copy()
    e[parent_col] = _coerce_id_series(e[parent_col])
    e[child_col] = _coerce_id_series(e[child_col])
    e = e.dropna(subset=[parent_col, child_col])

    return e[e[parent_col].isin(node_ids) & e[child_col].isin(node_ids)].copy()


def _ensure_top_col(nodes: pd.DataFrame, *, top_col: str, activity_col: str) -> pd.DataFrame:
    """
    Ensure nodes[top_col] exists and has at least some 1s.
    If missing/empty -> compute top10 OVERALL by activity (robust default).
    """
    n = nodes.copy()
    has_top = top_col in n.columns
    top_sum = (
        pd.to_numeric(n[top_col], errors="coerce").fillna(0).astype(int).sum()
        if has_top
        else 0
    )

    if (not has_top) or (top_sum == 0):
        n[top_col] = 0
        if activity_col in n.columns and n[activity_col].notna().any():
            act = pd.to_numeric(n[activity_col], errors="coerce")
            idx = act.nlargest(10).index
            n.loc[idx, top_col] = 1
    else:
        n[top_col] = pd.to_numeric(n[top_col], errors="coerce").fillna(0).astype(int)

    return n

 
def _filter_subgraph_top10_and_ancestors(
    nodes: pd.DataFrame,
    edges: pd.DataFrame | None,
    *,
    mode: SubgraphMode,
    node_id_col: str,
    parent_col: str,
    child_col: str,
    top_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Keep only top10 nodes and their ancestors, if top_col is available."""
    if mode == "all" or edges is None or edges.empty or top_col not in nodes.columns:
        return nodes, edges

    n = nodes.copy()
    n[node_id_col] = _coerce_id_series(n[node_id_col])

    top_raw = pd.to_numeric(n[top_col], errors="coerce").fillna(0).astype(int)
    top_ids = set(n.loc[top_raw == 1, node_id_col].dropna().tolist())
    if not top_ids:
        return nodes, edges

    e = edges.copy()
    e[parent_col] = _coerce_id_series(e[parent_col])
    e[child_col] = _coerce_id_series(e[child_col])
    e = e.dropna(subset=[parent_col, child_col])

    parent_map: dict[Hashable, Hashable] = dict(zip(e[child_col], e[parent_col]))

    # BFS-style walk up ancestor chains from each top-10 node.
    keep: set[Hashable] = set(top_ids)
    stack = list(top_ids)
    while stack:
        cid = stack.pop()
        pid = parent_map.get(cid)
        if pid is not None and pid not in keep:
            keep.add(pid)
            stack.append(pid)

    n_f = n[n[node_id_col].isin(keep)].copy()
    e_f = e[e[child_col].isin(keep) & e[parent_col].isin(keep)].copy()
    return n_f, e_f


def _order_by_parent(
    df: pd.DataFrame,
    edges: pd.DataFrame | None,
    *,
    node_id_col: str,
    generation_col: str,
    parent_col: str,
    child_col: str,
) -> pd.DataFrame:
    """Reorder nodes within generations so children cluster near parents."""
    if edges is None or edges.empty:
        return df

    d = df.copy()
    d["_vid"] = _coerce_id_series(d[node_id_col])
    d = d.dropna(subset=["_vid"])

    e = edges.copy()
    e[parent_col] = _coerce_id_series(e[parent_col])
    e[child_col] = _coerce_id_series(e[child_col])
    e = e.dropna(subset=[parent_col, child_col])

    parent = dict(zip(e[child_col], e[parent_col]))

    d["_ord"] = d.groupby(generation_col, sort=False).cumcount().astype(float)

    # Two passes: propagate parent ordering to children, then re-sort.
    for _ in range(2):
        ord_map = dict(zip(d["_vid"], d["_ord"]))
        d["_pord"] = d["_vid"].map(lambda vid: ord_map.get(parent.get(vid, None), np.nan))
        d["_key"] = d["_pord"].fillna(d["_ord"])
        d = d.sort_values([generation_col, "_key"], kind="mergesort")
        d["_ord"] = d.groupby(generation_col, sort=False).cumcount().astype(float)

    return d.drop(columns=["_ord", "_pord", "_key", "_vid"])


def _assign_x_from_current_order(
    df: pd.DataFrame,
    cfg: PlotConfig,
    *,
    node_id_col: str,
    generation_col: str,
) -> pd.DataFrame:
    """Recompute x jitter from existing row order within each generation (so parent-ordering actually shows)."""
    out = df.copy()
    out[generation_col] = pd.to_numeric(out[generation_col], errors="coerce")
    out = out.sort_values([generation_col], kind="mergesort")

    out["_rank"] = out.groupby(generation_col, sort=False).cumcount()
    n_in_gen = out.groupby(generation_col, sort=False)[node_id_col].transform("size")

    out["x"] = out[generation_col].astype(int)
    if cfg.x_jitter > 0:
        denom = (n_in_gen - 1).astype(float).where((n_in_gen - 1) > 0, 1.0)
        jitter = ((out["_rank"] - (n_in_gen - 1) / 2) / denom) * cfg.x_jitter
        out["x"] = out["x"] + jitter

    return out.drop(columns=["_rank"])


def _assign_y_rank_mode(
    df: pd.DataFrame,
    cfg: PlotConfig,
    *,
    node_id_col: str,
    generation_col: str,
) -> pd.DataFrame:
    """Recompute y from existing row order within each generation for y_mode='rank'."""
    out = df.copy()
    out = out.sort_values([generation_col], kind="mergesort")

    rank = out.groupby(generation_col, sort=False).cumcount()
    n_in_gen = out.groupby(generation_col, sort=False)[node_id_col].transform("size")
    base = (n_in_gen - 1 - rank).astype(float)

    if cfg.layout_mode == "stack":
        out["y"] = base
    else:
        denom = (n_in_gen - 1).astype(float).where((n_in_gen - 1) > 0, 1.0)
        out["y"] = (base / denom) * cfg.pack_generation_height

    return out


def _layout_nodes(
    nodes: pd.DataFrame,
    cfg: PlotConfig,
    *,
    node_id_col: str,
    generation_col: str,
    activity_col: str = "activity_score",
) -> pd.DataFrame:
    """Compute x/y positions for every node based on generation and activity/rank.

    Nodes are sorted within each generation by plasmid variant index (preferred),
    activity score, or raw ID, then assigned jittered x and either activity-based
    or rank-based y coordinates.

    Args:
        nodes: DataFrame containing at least *node_id_col* and *generation_col*.
        cfg: Plot configuration controlling jitter, y-mode, etc.
        node_id_col: Column name used as the unique node identifier.
        generation_col: Column name for the generation/round number.
        activity_col: Column name for the activity score (used when
            ``cfg.y_mode == 'activity'``).

    Returns:
        A copy of *nodes* with added ``x`` and ``y`` columns.
    """
    _require_columns(nodes, {node_id_col, generation_col}, "nodes")
    df = nodes.copy()

    df[generation_col] = pd.to_numeric(df[generation_col], errors="coerce")
    if df[generation_col].isna().all():
        raise ValueError(f"nodes['{generation_col}'] could not be parsed as numeric")

    sort_cols: list[str] = [generation_col]
    ascending: list[bool] = [True]

    if "plasmid_variant_index" in df.columns:
        df["_pidx_num"] = pd.to_numeric(df["plasmid_variant_index"], errors="coerce")
        df["_pidx_str"] = df["plasmid_variant_index"].astype(str)
        sort_cols.extend(["_pidx_num", "_pidx_str"])
        ascending.extend([True, True])
    elif activity_col in df.columns and df[activity_col].notna().any():
        df["_act"] = pd.to_numeric(df[activity_col], errors="coerce")
        sort_cols.append("_act")
        ascending.append(False)
    else:
        sort_cols.append(node_id_col)
        ascending.append(True)

    df = df.sort_values(sort_cols, ascending=ascending, kind="mergesort")

    # x with jitter
    df = _assign_x_from_current_order(df, cfg, node_id_col=node_id_col, generation_col=generation_col)

    # y
    if cfg.y_mode == "activity" and activity_col in df.columns:
        act = pd.to_numeric(df[activity_col], errors="coerce")
        if act.notna().any():
            df["y"] = act
        else:
            df = _assign_y_rank_mode(df, cfg, node_id_col=node_id_col, generation_col=generation_col)
    else:
        df = _assign_y_rank_mode(df, cfg, node_id_col=node_id_col, generation_col=generation_col)

    for c in ["_pidx_num", "_pidx_str", "_act"]:
        if c in df.columns:
            df = df.drop(columns=[c])

    return df


def _build_pos(df: pd.DataFrame, *, node_id_col: str) -> Mapping[Hashable, tuple[float, float]]:
    """Build a ``{node_id: (x, y)}`` position mapping from the laid-out DataFrame."""
    ids = _coerce_id_series(df[node_id_col])
    valid = ids.notna()
    if not valid.any():
        raise ValueError(f"nodes['{node_id_col}'] has no valid IDs")

    tmp = df.loc[valid, ["x", "y"]].copy()
    tmp.index = ids.loc[valid]
    tmp = tmp[~tmp.index.duplicated(keep="first")]

    return {k: (float(v["x"]), float(v["y"])) for k, v in tmp.to_dict("index").items()}


def _node_label(
    row: pd.Series,
    *,
    generation_col: str,
    node_id_col: str,
    label_id_source: LabelIdSource,
) -> str:
    """Format a concise on-plot label string such as ``G2:14`` for a single node."""
    gen = int(row[generation_col])
    if label_id_source == "plasmid_variant_index":
        if "plasmid_variant_index" in row and pd.notna(row["plasmid_variant_index"]):
            raw = row["plasmid_variant_index"]
            maybe_num = pd.to_numeric(pd.Series([raw]), errors="coerce").iloc[0]
            if pd.notna(maybe_num) and float(maybe_num).is_integer():
                return f"G{gen}:{int(maybe_num)}"
            return f"G{gen}:{raw}"
    if pd.notna(row.get(node_id_col)):
        return f"G{gen}:{row[node_id_col]}"
    return f"G{gen}"


def _compute_lineage_ids(
    nodes: pd.DataFrame,
    edges: pd.DataFrame | None,
    *,
    node_id_col: str,
    parent_col: str,
    child_col: str,
) -> pd.Series:
    """Map each node to its root ancestor ID by traversing parent edges.

    Nodes that share the same root belong to the same lineage, which is used
    for categorical colour assignment.
    """
    if edges is None or edges.empty:
        return _coerce_id_series(nodes[node_id_col])

    e = edges.copy()
    e[parent_col] = _coerce_id_series(e[parent_col])
    e[child_col] = _coerce_id_series(e[child_col])
    e = e.dropna(subset=[parent_col, child_col])
    parent_map: dict[Hashable, Hashable] = dict(zip(e[child_col], e[parent_col]))

    lineage: dict[Hashable, Hashable] = {}

    def _root(node: Hashable) -> Hashable:
        """Traverse parent links to the root ancestor, with cycle protection."""
        seen: set[Hashable] = set()
        cur = node
        while cur in parent_map and cur not in seen:
            seen.add(cur)
            cur = parent_map[cur]
        return cur

    vids = _coerce_id_series(nodes[node_id_col])
    for vid in vids.dropna().tolist():
        lineage[vid] = _root(vid)

    return vids.map(lineage)


def _compute_highlight_nodes(
    df: pd.DataFrame,
    edges: pd.DataFrame | None,
    cfg: PlotConfig,
    *,
    node_id_col: str,
    generation_col: str,
    parent_col: str,
    child_col: str,
    activity_col: str = "activity_score",
) -> set[Hashable]:
    """Return the set of node IDs to visually emphasise.

    Selects the top-k variants per generation (by activity) and walks
    parent edges upward to include their full ancestor chains.
    """
    if cfg.highlight_top_k_per_generation <= 0:
        return set()
    if activity_col not in df.columns:
        return set()

    tmp = df[[node_id_col, generation_col, activity_col]].copy()
    tmp[activity_col] = pd.to_numeric(tmp[activity_col], errors="coerce")
    tmp = tmp.dropna(subset=[activity_col])
    if tmp.empty:
        return set()

    topk = (
        tmp.sort_values([generation_col, activity_col], ascending=[True, False])
        .groupby(generation_col, sort=False)
        .head(cfg.highlight_top_k_per_generation)
    )
    keep = set(_coerce_id_series(topk[node_id_col]).dropna().tolist())

    if edges is None or edges.empty:
        return keep

    e = edges.copy()
    e[parent_col] = _coerce_id_series(e[parent_col])
    e[child_col] = _coerce_id_series(e[child_col])
    e = e.dropna(subset=[parent_col, child_col])
    parent_map = dict(zip(e[child_col], e[parent_col]))

    stack = list(keep)
    while stack:
        cid = stack.pop()
        pid = parent_map.get(cid)
        if pid is not None and pid not in keep:
            keep.add(pid)
            stack.append(pid)

    return keep


def _resolve_color(
    df: pd.DataFrame,
    edges: pd.DataFrame | None,
    cfg: PlotConfig,
    *,
    node_id_col: str,
    parent_col: str,
    child_col: str,
    activity_col: str = "activity_score",
    mutations_col: str = "protein_mutations",
) -> tuple[np.ndarray | None, Normalize | None, str | None, str | None]:
    """
    Returns: (color_vals, color_norm, cmap, colorbar_label)

    NOTE:
    - If mutations_col doesn't parse as numeric, we fall back to lineage.
    - We only show a colorbar for continuous metrics with a label (activity/mutations).
    """
    if cfg.color_mode == "none":
        return None, None, None, None

    color_vals: np.ndarray | None = None
    cmap: str = cfg.cmap_continuous
    cbar_label: str | None = None

    if cfg.color_mode == "activity" and activity_col in df.columns:
        color_vals = pd.to_numeric(df[activity_col], errors="coerce").to_numpy()
        cbar_label = "Activity score"
        cmap = cfg.cmap_continuous

    elif cfg.color_mode == "mutations":
        if mutations_col in df.columns:
            vals = pd.to_numeric(df[mutations_col], errors="coerce").to_numpy()
            if np.isfinite(vals).any():
                color_vals = vals
                cbar_label = "Mutations vs WT"
                cmap = cfg.cmap_continuous

        if color_vals is None:
            # fallback to lineage categorical
            lineage_ids = _compute_lineage_ids(df, edges, node_id_col=node_id_col, parent_col=parent_col, child_col=child_col)
            codes, _ = pd.factorize(lineage_ids)
            color_vals = codes.astype(float)
            cbar_label = None
            cmap = cfg.cmap_categorical

    elif cfg.color_mode == "lineage":
        lineage_ids = _compute_lineage_ids(df, edges, node_id_col=node_id_col, parent_col=parent_col, child_col=child_col)
        codes, _ = pd.factorize(lineage_ids)
        color_vals = codes.astype(float)
        cbar_label = None
        cmap = cfg.cmap_categorical

    norm: Normalize | None = None
    if color_vals is not None:
        finite = np.isfinite(color_vals)
        if finite.any():
            norm = Normalize(vmin=float(np.nanmin(color_vals)), vmax=float(np.nanmax(color_vals)))

    return color_vals, norm, cmap, cbar_label


def _enforce_consecutive_edges(
    edges: pd.DataFrame | None,
    df_nodes: pd.DataFrame,
    *,
    cfg: PlotConfig,
    node_id_col: str,
    generation_col: str,
    parent_col: str,
    child_col: str,
) -> pd.DataFrame | None:
    """Drop edges that jump across multiple generations (optional, but makes the plot feel like DE rounds)."""
    if not cfg.enforce_consecutive_generations:
        return edges
    if edges is None or edges.empty:
        return edges

    gen_map = dict(zip(_coerce_id_series(df_nodes[node_id_col]), pd.to_numeric(df_nodes[generation_col], errors="coerce").astype("Int64")))
    e = edges.copy()
    e["_gp"] = e[parent_col].map(gen_map)
    e["_gc"] = e[child_col].map(gen_map)
    e = e.dropna(subset=["_gp", "_gc"])
    e = e[(e["_gc"] - e["_gp"]) == 1]
    return e.drop(columns=["_gp", "_gc"])


def compute_top_variants_branch_trend(
    nodes: pd.DataFrame,
    edges: pd.DataFrame | None,
    *,
    node_id_col: str = "variant_id",
    generation_col: str = "generation_number",
    activity_col: str = "activity_score",
    top_col: str = "is_top10",
    parent_col: str = "parent_id",
    child_col: str = "child_id",
    top_n: int = 10,
    min_points: int = 3,
) -> BranchTrendStats:
    """Compute trend stats over the ancestor branches of the top-N variants."""
    if nodes is None or nodes.empty:
        return BranchTrendStats(tuple(), 0, False, None, None, None, None)

    df = nodes.copy()
    ids = _coerce_id_series(df[node_id_col])
    activity = pd.to_numeric(df[activity_col], errors="coerce")
    valid = ids.notna() & activity.notna()
    if not valid.any():
        return BranchTrendStats(tuple(), 0, False, None, None, None, None)

    dfv = df.loc[valid, [node_id_col, generation_col, activity_col]].copy()
    dfv[node_id_col] = _coerce_id_series(dfv[node_id_col])
    dfv[activity_col] = pd.to_numeric(dfv[activity_col], errors="coerce")

    if top_col in df.columns:
        top_mask = pd.to_numeric(df[top_col], errors="coerce").fillna(0).astype(int) == 1
        top_df = df.loc[top_mask, [node_id_col, activity_col]].copy()
        top_df[node_id_col] = _coerce_id_series(top_df[node_id_col])
        top_df[activity_col] = pd.to_numeric(top_df[activity_col], errors="coerce")
        top_df = top_df.dropna(subset=[node_id_col, activity_col]).sort_values(activity_col, ascending=False)
    else:
        top_df = pd.DataFrame(columns=[node_id_col, activity_col])

    if top_df.empty:
        top_df = dfv[[node_id_col, activity_col]].sort_values(activity_col, ascending=False)

    top_ids = tuple(top_df[node_id_col].head(top_n).tolist())
    if not top_ids:
        return BranchTrendStats(tuple(), 0, False, None, None, None, None)

    branch_ids: set[Hashable] = set(top_ids)
    if edges is not None and not edges.empty:
        e = edges.copy()
        e[parent_col] = _coerce_id_series(e[parent_col])
        e[child_col] = _coerce_id_series(e[child_col])
        e = e.dropna(subset=[parent_col, child_col])
        parent_map = dict(zip(e[child_col], e[parent_col]))

        for vid in top_ids:
            seen: set[Hashable] = set()
            cur = vid
            while cur in parent_map and cur not in seen:
                seen.add(cur)
                cur = parent_map[cur]
                branch_ids.add(cur)

    bmask = dfv[node_id_col].isin(branch_ids)
    x = pd.to_numeric(dfv.loc[bmask, generation_col], errors="coerce")
    y = pd.to_numeric(dfv.loc[bmask, activity_col], errors="coerce")
    valid_xy = ~(x.isna() | y.isna())
    x_arr = x[valid_xy].to_numpy(dtype=float)
    y_arr = y[valid_xy].to_numpy(dtype=float)

    trend_ready = (
        len(x_arr) >= min_points
        and np.unique(x_arr).size > 1
        and np.unique(y_arr).size > 1
    )
    if not trend_ready:
        return BranchTrendStats(top_ids, int(len(x_arr)), False, None, None, None, None)

    slope, intercept = np.polyfit(x_arr, y_arr, 1)
    x_line = (float(np.min(x_arr)), float(np.max(x_arr)))
    y_line = (float(slope * x_line[0] + intercept), float(slope * x_line[1] + intercept))

    r_val: float | None = None
    p_val: float | None = None
    if linregress is not None:
        try:
            stats = linregress(x_arr, y_arr)
            r_val = float(stats.rvalue)
            p_val = float(stats.pvalue)
        except ValueError:
            r_val = None
            p_val = None
    if r_val is None and np.std(x_arr) > 0 and np.std(y_arr) > 0:
        r_val = float(np.corrcoef(x_arr, y_arr)[0, 1])

    return BranchTrendStats(top_ids, int(len(x_arr)), True, r_val, p_val, x_line, y_line)


# -----------------------------
# main
# -----------------------------
def plot_layered_lineage(
    nodes: pd.DataFrame,
    edges: pd.DataFrame | None,
    out_path: str | Path | PathLike[str],
    *,
    node_id_col: str = "variant_id",
    generation_col: str = "generation_number",
    parent_col: str = "parent_id",
    child_col: str = "child_id",
    top_col: str = "is_top10",
    activity_col: str = "activity_score",
    mutations_col: str = "protein_mutations",
    config: PlotConfig = PlotConfig(),
) -> None:
    """Render the lineage visualisation for a single experiment."""
    if nodes is None or nodes.empty:
        raise ValueError("nodes is empty; nothing to plot")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 0) ensure top_col usable
    nodes2 = _ensure_top_col(nodes, top_col=top_col, activity_col=activity_col)

    # 1) edges filtered to nodes
    edges2 = _filter_edges_to_nodes(nodes2, edges, node_id_col=node_id_col, parent_col=parent_col, child_col=child_col)

    # 2) subgraph filtering
    nodes_f, edges_f = _filter_subgraph_top10_and_ancestors(
        nodes2, edges2, mode=config.subgraph_mode,
        node_id_col=node_id_col, parent_col=parent_col, child_col=child_col, top_col=top_col
    )

    # 3) only connected nodes (optional)
    if config.only_connected_nodes:
        if edges_f is not None and not edges_f.empty:
            n = nodes_f.copy()
            n[node_id_col] = _coerce_id_series(n[node_id_col])
            e = edges_f.copy()
            e[parent_col] = _coerce_id_series(e[parent_col])
            e[child_col] = _coerce_id_series(e[child_col])
            connected = set(e[parent_col].dropna().tolist()) | set(e[child_col].dropna().tolist())
            nodes_f = n[n[node_id_col].isin(connected)].copy()
        else:
            nodes_f = nodes_f.iloc[0:0].copy()

    if nodes_f.empty:
        fig, ax = plt.subplots(figsize=config.figsize)
        ax.set_title(config.title, fontsize=16)
        ax.text(0.5, 0.5, "No nodes to plot after filtering", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        fig.tight_layout(pad=1.6)
        fig.savefig(out_path, dpi=config.dpi)
        plt.close(fig)
        return

    # 4) layout
    df = _layout_nodes(nodes_f, config, node_id_col=node_id_col, generation_col=generation_col, activity_col=activity_col)

    # 5) order-by-parent then recompute jitter so the ordering matters
    if config.parent_sorted_layout and edges_f is not None and not edges_f.empty:
        df = _order_by_parent(df, edges_f, node_id_col=node_id_col, generation_col=generation_col, parent_col=parent_col, child_col=child_col)
        df = _assign_x_from_current_order(df, config, node_id_col=node_id_col, generation_col=generation_col)
        if config.y_mode == "rank":
            df = _assign_y_rank_mode(df, config, node_id_col=node_id_col, generation_col=generation_col)

    pos = _build_pos(df, node_id_col=node_id_col)

    # edge data
    eplot: pd.DataFrame | None = None
    if edges_f is not None and not edges_f.empty:
        eplot = edges_f.copy()
        eplot[parent_col] = _coerce_id_series(eplot[parent_col])
        eplot[child_col] = _coerce_id_series(eplot[child_col])
        eplot = eplot.dropna(subset=[parent_col, child_col])

    # optional: drop long jump edges
    eplot = _enforce_consecutive_edges(
        eplot, df, cfg=config,
        node_id_col=node_id_col, generation_col=generation_col, parent_col=parent_col, child_col=child_col
    )

    # masks
    is_top = pd.to_numeric(df.get(top_col, 0), errors="coerce").fillna(0).astype(int).to_numpy()
    mask_top = is_top == 1

    # color
    color_vals, color_norm, color_cmap, cbar_label = _resolve_color(
        df, eplot, config,
        node_id_col=node_id_col, parent_col=parent_col, child_col=child_col,
        activity_col=activity_col, mutations_col=mutations_col
    )

    # highlight set
    highlight_nodes = _compute_highlight_nodes(
        df, eplot, config,
        node_id_col=node_id_col, generation_col=generation_col,
        parent_col=parent_col, child_col=child_col, activity_col=activity_col
    )

    # dynamic label offset
    if config.y_mode == "activity":
        y = pd.to_numeric(df["y"], errors="coerce")
        yr = float(y.max() - y.min()) if y.notna().any() else 1.0
        label_offset = config.label_offset_frac_of_yrange * (yr if yr > 0 else 1.0)
    else:
        label_offset = config.label_offset_rank_units

    fig, ax = plt.subplots(figsize=config.figsize)

    # edges: base then highlighted
    if eplot is not None and not eplot.empty:
        for p_id, c_id in zip(eplot[parent_col].tolist(), eplot[child_col].tolist()):
            p = pos.get(p_id)
            c = pos.get(c_id)
            if p is None or c is None:
                continue
            ax.plot([p[0], c[0]], [p[1], c[1]],
                    linewidth=config.edge_lw, alpha=config.edge_alpha,
                    color=config.edge_color, zorder=1)

        if highlight_nodes:
            node_to_color = dict(zip(_coerce_id_series(df[node_id_col]), color_vals)) if color_vals is not None else None
            for p_id, c_id in zip(eplot[parent_col].tolist(), eplot[child_col].tolist()):
                if p_id not in highlight_nodes or c_id not in highlight_nodes:
                    continue
                p = pos.get(p_id)
                c = pos.get(c_id)
                if p is None or c is None:
                    continue
                edge_col = config.edge_color
                if node_to_color is not None and color_norm is not None and color_cmap is not None:
                    edge_col = plt.cm.get_cmap(color_cmap)(color_norm(node_to_color.get(c_id, 0.0)))
                ax.plot([p[0], c[0]], [p[1], c[1]],
                        linewidth=config.edge_lw + config.edge_lw_top_boost,
                        alpha=config.edge_alpha_top,
                        color=edge_col, zorder=2)

    # nodes: non-top
    ax.scatter(
        df.loc[~mask_top, "x"], df.loc[~mask_top, "y"],
        s=config.node_size,
        c=(color_vals[~mask_top] if color_vals is not None else None),
        norm=color_norm, cmap=color_cmap,
        alpha=config.non_top_alpha,
        linewidths=0.0 if config.lw_other == 0.0 else config.lw_other,
        edgecolors="none" if config.lw_other == 0.0 else config.node_edgecolor,
        zorder=2,
    )

    # nodes: top
    sc = ax.scatter(
        df.loc[mask_top, "x"], df.loc[mask_top, "y"],
        s=config.node_size + config.top10_size_boost,
        c=(color_vals[mask_top] if color_vals is not None else None),
        norm=color_norm, cmap=color_cmap,
        alpha=config.top_alpha,
        linewidths=config.lw_top10, edgecolors=config.node_edgecolor,
        zorder=3,
    )

    # labels
    if config.label_mode != "none":
        if config.label_mode == "topk":
            if config.label_top_k_per_generation > 0 and activity_col in df.columns:
                label_cols = [node_id_col, generation_col, activity_col, top_col, "x", "y"]
                if "plasmid_variant_index" in df.columns:
                    label_cols.append("plasmid_variant_index")
                tmp = df[label_cols].copy()
                tmp[activity_col] = pd.to_numeric(tmp[activity_col], errors="coerce")
                tmp = tmp.dropna(subset=[activity_col])
                if not tmp.empty:
                    df_for_labels = (
                        tmp.sort_values([generation_col, activity_col], ascending=[True, False])
                        .groupby(generation_col, sort=False)
                        .head(config.label_top_k_per_generation)
                    )
                else:
                    label_cols = [node_id_col, generation_col, top_col, "x", "y"]
                    if "plasmid_variant_index" in df.columns:
                        label_cols.append("plasmid_variant_index")
                    df_for_labels = df.loc[mask_top, label_cols]
            else:
                label_cols = [node_id_col, generation_col, top_col, "x", "y"]
                if "plasmid_variant_index" in df.columns:
                    label_cols.append("plasmid_variant_index")
                df_for_labels = df.loc[mask_top, label_cols]
        else:  # "all"
            if config.max_labels_per_generation is not None:
                df_for_labels = (
                    df.assign(_r=df.groupby(generation_col, sort=False).cumcount())
                    .loc[lambda d: d["_r"] < config.max_labels_per_generation]
                    .drop(columns="_r")
                )
            else:
                df_for_labels = df

        for _, row in df_for_labels.iterrows():
            top = int(pd.to_numeric(row.get(top_col, 0), errors="coerce") or 0) == 1
            base = _node_label(
                row,
                generation_col=generation_col,
                node_id_col=node_id_col,
                label_id_source=config.label_id_source,
            )
            label = f"★ {base}" if top else base
            ax.text(float(row["x"]), float(row["y"]) + float(label_offset),
                    label, ha="center", va="bottom",
                    fontsize=config.label_fontsize, zorder=4)

    # Optional overlay: top-10 branch trendline (enabled by route toggle).
    if config.show_top10_branch_trend and config.y_mode == "activity":
        trend = compute_top_variants_branch_trend(
            df,
            eplot,
            node_id_col=node_id_col,
            generation_col=generation_col,
            activity_col=activity_col,
            top_col=top_col,
            parent_col=parent_col,
            child_col=child_col,
            top_n=10,
            min_points=config.top10_branch_trend_min_points,
        )
        if trend.trend_ready and trend.x_line and trend.y_line:
            ax.plot(
                np.array([trend.x_line[0], trend.x_line[1]], dtype=float),
                np.array([trend.y_line[0], trend.y_line[1]], dtype=float),
                color="#0f766e",
                linewidth=2.4,
                linestyle="-.",
                alpha=0.95,
                zorder=5,
            )

    # axes styling (CRITICAL FIX: ticks from generation integers, not jittered x)
    ax.set_title(config.title, fontsize=16)
    ax.set_xlabel("Generation", fontsize=12)

    gens = np.sort(pd.to_numeric(df[generation_col], errors="coerce").dropna().astype(int).unique())
    if gens.size:
        ax.set_xticks(gens)
        ax.set_xlim(int(gens.min()) - 0.6, int(gens.max()) + 0.6)

    if config.y_mode == "activity":
        ax.set_ylabel("Activity score", fontsize=12)
    else:
        ax.set_ylabel("")
        ax.set_yticks([])

    if config.show_generation_grid:
        ax.grid(True, axis="x", linewidth=1.2, alpha=0.30)
    if config.show_horizontal_grid:
        ax.grid(True, axis="y", linewidth=0.7, alpha=0.18)

    # colorbar only for continuous metrics
    if color_vals is not None and color_norm is not None and cbar_label is not None:
        fig.colorbar(sc, ax=ax, label=cbar_label)

    if config.show_figure_border:
        fig.add_artist(Rectangle((0, 0), 1, 1, transform=fig.transFigure, fill=False, edgecolor="black", linewidth=2.2))

    fig.tight_layout(pad=1.6)
    fig.savefig(out_path, dpi=config.dpi)
    plt.close(fig)


def plot_relative_expression_trend(
    trend: pd.DataFrame,
    out_path: str | Path | PathLike[str],
    *,
    title: str = "Relative Expression by Generation",
    figsize: tuple[float, float] = (14, 4.2),
    dpi: int = 220,
    pvalue: float | None = None,
    rvalue: float | None = None,
) -> None:
    """Render a generation-wise relative-expression trend line."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=figsize)

    if trend is None or trend.empty:
        ax.set_title(title, fontsize=15)
        ax.text(
            0.5,
            0.5,
            "No relative expression data available",
            ha="center",
            va="center",
            transform=ax.transAxes,
            fontsize=11,
            color="#5f7085",
        )
        ax.set_axis_off()
    else:
        x = pd.to_numeric(trend["generation_number"], errors="coerce")
        mean_y = pd.to_numeric(trend["mean_relative_expression"], errors="coerce")
        min_y = pd.to_numeric(trend["min_relative_expression"], errors="coerce")
        max_y = pd.to_numeric(trend["max_relative_expression"], errors="coerce")

        valid = ~(x.isna() | mean_y.isna())
        x = x[valid].to_numpy(dtype=float)
        mean_arr = mean_y[valid].to_numpy(dtype=float)
        min_arr = min_y[valid].to_numpy(dtype=float)
        max_arr = max_y[valid].to_numpy(dtype=float)

        ax.set_title(title, fontsize=15)
        ax.axhline(
            1.0,
            color="#d64545",
            linestyle="--",
            linewidth=1.4,
            alpha=0.85,
            label="Baseline = 1.0",
        )

        if len(x):
            ax.fill_between(
                x,
                min_arr,
                max_arr,
                color="#7cb5ec",
                alpha=0.22,
                linewidth=0,
                label="Generation range",
            )
            ax.plot(
                x,
                mean_arr,
                color="#0b5fff",
                linewidth=2.8,
                marker="o",
                markersize=6.5,
                markerfacecolor="#ffffff",
                markeredgecolor="#0b5fff",
                markeredgewidth=1.5,
                label="Mean relative expression",
                zorder=3,
            )

            # Add a fitted correlation line so users can see overall expression trend direction.
            if len(x) >= 2 and np.unique(x).size >= 2:
                try:
                    slope, intercept = np.polyfit(x, mean_arr, 1)
                    fit_y = slope * x + intercept
                    ax.plot(
                        x,
                        fit_y,
                        color="#0f766e",
                        linewidth=2.0,
                        linestyle="-.",
                        alpha=0.95,
                        label="Correlation trend line",
                        zorder=2,
                    )
                except Exception:
                    # Keep plotting robust even if fit cannot be computed on degenerate input.
                    pass

                if rvalue is None and np.std(x) > 0 and np.std(mean_arr) > 0:
                    rvalue = float(np.corrcoef(x, mean_arr)[0, 1])

                if pvalue is not None and np.isfinite(pvalue):
                    p_label = "<0.001" if pvalue < 0.001 else f"{pvalue:.3f}"
                else:
                    p_label = "n/a"
                r_label = f"{rvalue:.3f}" if (rvalue is not None and np.isfinite(rvalue)) else "n/a"
                stats_text = f"r = {r_label} | p = {p_label}"
                ax.text(
                    0.985,
                    0.96,
                    stats_text,
                    transform=ax.transAxes,
                    ha="right",
                    va="top",
                    fontsize=9.5,
                    color="#0f172a",
                    bbox={
                        "boxstyle": "round,pad=0.28",
                        "facecolor": "white",
                        "edgecolor": "#cbd5e1",
                        "alpha": 0.9,
                    },
                    zorder=4,
                )

        ax.set_xlabel("Generation", fontsize=11)
        ax.set_ylabel("Relative expression", fontsize=11)
        if len(x):
            ax.set_xticks(sorted({int(v) for v in x}))
            ymin = np.nanmin(np.concatenate([min_arr, [1.0]]))
            ymax = np.nanmax(np.concatenate([max_arr, [1.0]]))
            pad = max((ymax - ymin) * 0.12, 0.2)
            ax.set_ylim(max(0.0, ymin - pad), ymax + pad)
        ax.grid(True, axis="y", linewidth=0.75, alpha=0.25)
        ax.grid(True, axis="x", linewidth=0.5, alpha=0.12)
        ax.legend(frameon=False, loc="upper left", fontsize=9)

    fig.tight_layout(pad=1.4)
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
