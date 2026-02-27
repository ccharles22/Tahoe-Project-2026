from __future__ import annotations

from dataclasses import dataclass, replace
from os import PathLike
from pathlib import Path
from typing import Iterable, Literal

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize

# Optional dependency (recommended)
try:
	import networkx as nx
except Exception:  # pragma: no cover
	nx = None


LabelMode = Literal["none", "top10", "all"]
NetworkMode = Literal["identity", "cooccurrence"]


@dataclass(frozen=True) #configuration for the protein similarity network plot, with defaults and type annotations
class ProteinNetConfig:
	# plotting
	figsize: tuple[float, float] = (14, 8)
	dpi: int = 200
	title: str = "Protein Similarity Network"
	label_mode: LabelMode = "top10"
	label_fontsize: int = 8

	# node styling
	node_size: float = 40.0
	top10_size_boost: float = 120.0
	non_top_alpha: float = 0.35
	top_alpha: float = 1.0
	top10_edgecolor: str = "black"
	top10_lw: float = 2.0

	# edges
	edge_alpha: float = 0.10
	edge_lw: float = 0.8

	# graph/layout
	spring_k: float | None = None         # None lets networkx choose
	spring_iterations: int = 200
	layout_seed: int = 7

	# similarity rule
	identity_threshold: float = 0.95      # connect if identity > this threshold
	mode: NetworkMode = "identity"         # identity = sequence; cooccurrence = shared mutations

	# co-occurrence rule (variant-variant edges from shared protein mutations)
	cooccur_min_shared_mutations: int = 1
	cooccur_jaccard_threshold: float | None = None
	cooccur_weight: Literal["shared", "jaccard"] = "shared"

	# diagnostics
	debug: bool = False

	# selection (keep it small so it looks like a network, not a hairball)
	top_n_by_activity: int = 250          # global cap; set smaller if slow
	always_include_top10: bool = True
	neighbors_per_top10: int = 25         # add close neighbors around top10
	max_nodes_final: int = 350            # hard cap after neighbor expansion

	# co-occurrence presentation
	cooccur_focus_top10_neighbors: bool = False


def _require_networkx() -> None:
	if nx is None:
		raise ImportError(
			"This plot requires networkx. Install it with:\n"
			"  pip install networkx"
		)


def _hamming_distance(a: str, b: str, *, max_dist: int) -> int | None:
	"""
	Hamming distance with early stop.
	Returns None if lengths differ or if distance exceeds max_dist.
	"""
	if a is None or b is None: #treat None as missing sequence, not comparable
		return None
	if len(a) != len(b):
		return None
	d = 0
	for ca, cb in zip(a, b):
		if ca != cb:
			d += 1
			if d > max_dist:
				return None
	return d


def _pick_nodes_for_network( 
	nodes: pd.DataFrame,
	cfg: ProteinNetConfig,
	*,
	id_col: str,
	activity_col: str,
	top_col: str,
	seq_col: str,
	require_seq: bool = True,
) -> pd.DataFrame:
	"""
	Choose a manageable subset so the network is readable.
	Strategy:
	  - take top_n_by_activity
	  - ensure top10 included
	  - then add neighbors around top10 by sequence distance (cheap-ish)
	"""
	n = nodes.copy()

	# clean columns
	if require_seq:
		n = n.dropna(subset=[id_col, seq_col]).copy()
	else:
		n = n.dropna(subset=[id_col]).copy()
	n[activity_col] = pd.to_numeric(n.get(activity_col), errors="coerce")
	n[top_col] = pd.to_numeric(n.get(top_col, 0), errors="coerce").fillna(0).astype(int)

	# base: top by activity (with NaNs pushed down)
	n = n.sort_values([activity_col], ascending=False, na_position="last")
	base = n.head(cfg.top_n_by_activity).copy()

	# ensure top10 are included
	if cfg.always_include_top10:
		top10 = n[n[top_col] == 1].copy()
		base_ids = set(base[id_col].tolist())
		add_top10 = top10[~top10[id_col].isin(base_ids)]
		base = pd.concat([base, add_top10], ignore_index=True)

	# expand around top10: pick nearest sequence neighbors within threshold,
	# capped per top10 to keep size reasonable.
	if cfg.neighbors_per_top10 > 0 and (base[top_col] == 1).any():
		pool = n  # full pool (but could also restrict to top_n_by_activity*2 if needed)
		base_ids = set(base[id_col].tolist())

		top10_rows = base[base[top_col] == 1][[id_col, seq_col]].dropna().copy()
		to_add: list[int] = []

		# Precompute sequences for pool (as python lists for speed)
		pool_ids = pool[id_col].tolist()
		pool_seqs = pool[seq_col].tolist()

		for _, r in top10_rows.iterrows():
			tseq = r[seq_col]
			if not isinstance(tseq, str) or not tseq:
				continue
			max_dist = int(np.floor((1.0 - cfg.identity_threshold) * len(tseq)))
			hits: list[tuple[int, int]] = []  # (dist, idx_in_pool)
			for i, (pid, pseq) in enumerate(zip(pool_ids, pool_seqs)):
				if pid in base_ids:
					continue
				d = _hamming_distance(tseq, pseq, max_dist=max_dist)
				if d is not None:
					hits.append((d, i))

			hits.sort(key=lambda x: x[0])
			for dist, i in hits[: cfg.neighbors_per_top10]:
				to_add.append(i)

		if to_add:
			add_df = pool.iloc[sorted(set(to_add))].copy()
			base = pd.concat([base, add_df], ignore_index=True)

	# hard cap final
	base = base.drop_duplicates(subset=[id_col]).copy()
	if len(base) > cfg.max_nodes_final:
		base = base.sort_values([top_col, activity_col], ascending=[False, False], na_position="last")
		base = base.head(cfg.max_nodes_final).copy()

	return base


def build_protein_similarity_edges( #build edges based on sequence identity above threshold; only for equal-length sequences; O(N^2) so keep input small
	nodes_sub: pd.DataFrame,
	*,
	id_col: str,
	seq_col: str,
	identity_threshold: float,
) -> pd.DataFrame:
	
	# WARNING: O(N^2) - keep nodes_sub small (<= ~400).
	ids = nodes_sub[id_col].tolist()
	seqs = nodes_sub[seq_col].tolist()

	edges: list[tuple[int, int, int]] = []  # (u, v, dist)
	n = len(ids)

	for i in range(n):
		si = seqs[i]
		for j in range(i + 1, n):
			sj = seqs[j]
			if len(si) != len(sj):
				continue
			max_dist = int(np.floor((1.0 - identity_threshold) * len(si)))
			d = _hamming_distance(si, sj, max_dist=max_dist)
			if d is None:
				continue
			identity = 1.0 - (d / len(si))
			if identity > identity_threshold:
				edges.append((ids[i], ids[j], identity))

	return pd.DataFrame(edges, columns=["u", "v", "identity"])


def _build_mutation_sets( 
	mutations: pd.DataFrame,
	*,
	variant_col: str,
	position_col: str,
	original_col: str,
	mutated_col: str,
) -> dict[int, set[str]]:
	sets: dict[int, set[str]] = {}
	if mutations is None or mutations.empty:
		return sets

	needed = {variant_col, position_col, original_col, mutated_col}
	if not needed.issubset(mutations.columns):
		return sets

	for r in mutations.itertuples(index=False):
		vid = getattr(r, variant_col)
		pos = getattr(r, position_col)
		orig = getattr(r, original_col)
		mut = getattr(r, mutated_col)
		if pd.isna(vid) or pd.isna(pos) or pd.isna(orig) or pd.isna(mut):
			continue
		label = f"{orig}{int(pos)}{mut}"
		sets.setdefault(int(vid), set()).add(label)

	return sets


def build_protein_cooccurrence_edges(
	nodes_sub: pd.DataFrame,
	mutations: pd.DataFrame,
	*,
	id_col: str,
	variant_col: str,
	position_col: str,
	original_col: str,
	mutated_col: str,
	min_shared: int,
	jaccard_threshold: float | None,
) -> pd.DataFrame:
	"""
	Build undirected edges when variants share protein mutations.
	Weights are both shared mutation count and Jaccard similarity.
	"""
	mut_sets = _build_mutation_sets(
		mutations,
		variant_col=variant_col,
		position_col=position_col,
		original_col=original_col,
		mutated_col=mutated_col,
	)

	ids = nodes_sub[id_col].tolist()
	edges: list[tuple[int, int, int, float]] = []
	for i in range(len(ids)):
		set_i = mut_sets.get(int(ids[i]), set())
		for j in range(i + 1, len(ids)):
			set_j = mut_sets.get(int(ids[j]), set())
			if not set_i or not set_j:
				continue
			shared = set_i & set_j
			shared_n = len(shared)
			if shared_n < min_shared:
				continue
			union = set_i | set_j
			jaccard = (shared_n / len(union)) if union else 0.0
			if jaccard_threshold is not None and jaccard < jaccard_threshold:
				continue
			edges.append((int(ids[i]), int(ids[j]), shared_n, float(jaccard)))

	return pd.DataFrame(edges, columns=["u", "v", "shared", "jaccard"])


def plot_protein_similarity_network(
	nodes: pd.DataFrame,
	out_path: str | Path | PathLike[str],
	*,
	# optional filtering: if you pass experiment_id, nodes should already be filtered upstream,
	# or include experiment_id in nodes and filter here.
	config: ProteinNetConfig = ProteinNetConfig(),
	mutations: pd.DataFrame | None = None,
	mode: NetworkMode | None = None,
	id_col: str = "variant_id",
	seq_col: str = "protein_sequence",
	activity_col: str = "activity_score",
	top_col: str = "is_top10",
) -> None:
	_require_networkx()

	if nodes is None or nodes.empty:
		raise ValueError("nodes is empty; nothing to plot")

	if mode is not None and mode != config.mode:
		config = replace(config, mode=mode)

	if config.mode == "cooccurrence":
		config = replace(config, neighbors_per_top10=0)

	out_path = Path(out_path)
	out_path.parent.mkdir(parents=True, exist_ok=True)

	# if top_col missing, create top10 by activity (overall)
	nodes2 = nodes.copy()
	if top_col not in nodes2.columns or pd.to_numeric(nodes2[top_col], errors="coerce").fillna(0).sum() == 0:
		if activity_col in nodes2.columns and nodes2[activity_col].notna().any():
			act = pd.to_numeric(nodes2[activity_col], errors="coerce")
			top_idx = act.nlargest(10).index
			nodes2[top_col] = 0
			nodes2.loc[top_idx, top_col] = 1
		else:
			nodes2[top_col] = 0

	# Choose subset
	sub = _pick_nodes_for_network(
		nodes2,
		config,
		id_col=id_col,
		activity_col=activity_col,
		top_col=top_col,
		seq_col=seq_col,
		require_seq=(config.mode == "identity"),
	)

	if sub.empty:
		fig, ax = plt.subplots(figsize=config.figsize)
		ax.set_title(config.title)
		ax.text(0.5, 0.5, "No sequences available to build similarity network", ha="center", va="center")
		ax.set_axis_off()
		fig.tight_layout()
		fig.savefig(out_path, dpi=config.dpi)
		plt.close(fig)
		return

	if config.debug:
		lengths = sub[seq_col].astype(str).str.len()
		print("Unique lengths:", lengths.nunique())

		# mutation spread (approx)
		def hd(a: str, b: str) -> int:
			return sum(x != y for x, y in zip(a, b))

		seqs = sub[seq_col].tolist()
		dists: list[int] = []
		for i in range(min(50, len(seqs))):
			for j in range(i + 1, min(50, len(seqs))):
				if len(seqs[i]) == len(seqs[j]):
					dists.append(hd(seqs[i], seqs[j]))

		print("Median pairwise dist:", np.median(dists))

	# Build edges
	if config.mode == "cooccurrence":
		edges = build_protein_cooccurrence_edges(
			sub,
			mutations,
			id_col=id_col,
			variant_col="variant_id",
			position_col="position",
			original_col="original",
			mutated_col="mutated",
			min_shared=config.cooccur_min_shared_mutations,
			jaccard_threshold=config.cooccur_jaccard_threshold,
		)
		if edges.empty:
			fig, ax = plt.subplots(figsize=config.figsize)
			ax.set_title(config.title)
			ax.text(
				0.5,
				0.5,
				"No shared protein mutations to build a co-occurrence network",
				ha="center",
				va="center",
			)
			ax.set_axis_off()
			fig.tight_layout()
			fig.savefig(out_path, dpi=config.dpi)
			plt.close(fig)
			return
	else:
		edges = build_protein_similarity_edges(
			sub,
			id_col=id_col,
			seq_col=seq_col,
			identity_threshold=config.identity_threshold,
		)

	# Build graph
	G = nx.Graph()
	for r in sub.itertuples(index=False):
		vid = getattr(r, id_col)
		G.add_node(vid)

	if config.mode == "cooccurrence":
		for u, v, shared, jaccard in edges.itertuples(index=False):
			weight = shared if config.cooccur_weight == "shared" else jaccard
			G.add_edge(u, v, weight=weight)
	else:
		for u, v, identity in edges.itertuples(index=False):
			G.add_edge(u, v, weight=identity)

	# top10 mask
	topmask = pd.to_numeric(sub[top_col], errors="coerce").fillna(0).astype(int)
	top_ids = set(sub.loc[topmask == 1, id_col].tolist())

	if config.mode == "cooccurrence" and config.cooccur_focus_top10_neighbors:
		focus_nodes = set(top_ids)
		for n in list(top_ids):
			if n in G:
				focus_nodes.update(G.neighbors(n))
		if focus_nodes:
			G = G.subgraph(focus_nodes).copy()
			sub = sub[sub[id_col].isin(focus_nodes)].copy()
			topmask = pd.to_numeric(sub[top_col], errors="coerce").fillna(0).astype(int)
			top_ids = set(sub.loc[topmask == 1, id_col].tolist())

	# Co-occurrence often produces multiple disconnected islands plus isolates.
	# For the static report, show the connected core so the network reads as one
	# coherent structure instead of scattered singletons.
	if config.mode == "cooccurrence" and G.number_of_edges() > 0:
		components = list(nx.connected_components(G))
		if len(components) > 1:
			largest = max(components, key=len)
			G = G.subgraph(largest).copy()
			sub = sub[sub[id_col].isin(largest)].copy()
			topmask = pd.to_numeric(sub[top_col], errors="coerce").fillna(0).astype(int)
			top_ids = set(sub.loc[topmask == 1, id_col].tolist())

	# Layout (spring = force-directed)
	pos = nx.spring_layout(
		G,
		seed=config.layout_seed,
		k=config.spring_k,
		iterations=config.spring_iterations,
		weight="weight",
	)

	# Color by activity
	act = pd.to_numeric(sub[activity_col], errors="coerce")
	node_to_act = dict(zip(sub[id_col], act))
	act_vals = np.array([node_to_act.get(n, np.nan) for n in G.nodes()], dtype=float)

	finite = np.isfinite(act_vals)
	norm = None
	if finite.any():
		norm = Normalize(vmin=float(np.nanmin(act_vals)), vmax=float(np.nanmax(act_vals)))

	# Plot
	fig, ax = plt.subplots(figsize=config.figsize)

	# edges
	if G.number_of_edges() > 0:
		nx.draw_networkx_edges(G, pos, ax=ax, alpha=config.edge_alpha, width=config.edge_lw)

	# nodes (split into non-top + top for styling)
	non_top_nodes = [n for n in G.nodes() if n not in top_ids]
	top_nodes = [n for n in G.nodes() if n in top_ids]

	def _node_colors(nodes_list: list[int]) -> np.ndarray | None:
		if norm is None:
			return None
		vals = np.array([node_to_act.get(n, np.nan) for n in nodes_list], dtype=float)
		return vals

	# Non-top
	nx.draw_networkx_nodes(
		G,
		pos,
		nodelist=non_top_nodes,
		node_size=config.node_size,
		node_color=_node_colors(non_top_nodes),
		cmap="viridis",
		alpha=config.non_top_alpha,
		linewidths=0.0,
		ax=ax,
		vmin=(norm.vmin if norm else None),
		vmax=(norm.vmax if norm else None),
	)

	# Top
	nx.draw_networkx_nodes(
		G,
		pos,
		nodelist=top_nodes,
		node_size=config.node_size + config.top10_size_boost,
		node_color=_node_colors(top_nodes),
		cmap="viridis",
		alpha=config.top_alpha,
		linewidths=config.top10_lw,
		edgecolors=config.top10_edgecolor,
		ax=ax,
		vmin=(norm.vmin if norm else None),
		vmax=(norm.vmax if norm else None),
	)

	# Labels
	if config.label_mode != "none":
		labels = {}
		if config.label_mode == "top10":
			for n in top_nodes:
				labels[n] = f"★ {n}"
		else:
			for n in G.nodes():
				labels[n] = str(n)
		nx.draw_networkx_labels(G, pos, labels=labels, font_size=config.label_fontsize, ax=ax)

	ax.set_title(config.title, fontsize=16)
	ax.set_axis_off()

	# Colorbar
	if norm is not None and finite.any():
		sm = plt.cm.ScalarMappable(cmap="viridis", norm=norm)
		sm.set_array([])
		fig.colorbar(sm, ax=ax, label="Activity score")

	fig.tight_layout(pad=1.0)
	fig.savefig(out_path, dpi=config.dpi)
	plt.close(fig)


# -----------------------------------------------------------------------------
# Optional: helper to fetch nodes from Postgres (drop-in if you want it here)
# -----------------------------------------------------------------------------
def fetch_nodes_for_experiment(conn, experiment_id: int) -> pd.DataFrame:
	"""
	Returns nodes with variant_id, protein_sequence, activity_score, generation_number, plasmid_variant_index.
	"""
	q = """
	SELECT
	  v.variant_id,
	  v.protein_sequence,
	  g.generation_number,
	  v.plasmid_variant_index,
	  m.value AS activity_score
	FROM variants v
	JOIN generations g ON g.generation_id = v.generation_id
	LEFT JOIN metrics m
	  ON m.variant_id = v.variant_id
	 AND m.metric_name = 'activity_score'
	 AND m.metric_type = 'derived'
	WHERE g.experiment_id = %s;
	"""
	return pd.read_sql(q, conn, params=(experiment_id,))
