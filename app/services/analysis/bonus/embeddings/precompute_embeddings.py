"""Compute and persist PCA/t-SNE embeddings for bonus visualisations."""

from __future__ import annotations

import argparse
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

from app.services.analysis.bonus.database.postgres import (
    bulk_insert_metrics,
    db_conn,
    delete_metrics_by_name,
    fetch_metric_definition_ids,
    refresh_materialized_view,
)
from app.services.analysis.bonus.features.mutation_vector import build_mutation_matrix


def fetch_variants_and_mutations(conn, generation_id: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch variants and nonsynonymous protein mutations for one generation."""
    variants = pd.read_sql_query(
        """
        SELECT variant_id, generation_id, plasmid_variant_index, parent_variant_id
        FROM variants
        WHERE generation_id = %s
        """,
        conn,
        params=(generation_id,),
    )

    muts = pd.read_sql_query(
        """
        SELECT variant_id, mutation_type, position, original, mutated, is_synonymous
        FROM mutations
        WHERE variant_id IN (
            SELECT variant_id FROM variants WHERE generation_id = %s
        )
        """,
        conn,
        params=(generation_id,),
    )
    return variants, muts


def compute_pca_xy(X: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Return two-dimensional PCA coordinates for the supplied feature matrix."""
    pca = PCA(n_components=2, random_state=seed)
    coords = pca.fit_transform(X.values)
    return pd.DataFrame({"variant_id": X.index, "pca_x": coords[:, 0], "pca_y": coords[:, 1]})


def compute_tsne_xy(X: pd.DataFrame, seed: int = 42, perplexity: int = 30) -> pd.DataFrame:
    """Return two-dimensional t-SNE coordinates when enough rows are present.

    Args:
        X: Feature matrix with variant_id as index.
        seed: Random seed for reproducibility.
        perplexity: t-SNE perplexity; auto-clamped to ``[2, n-1]``.

    Returns:
        DataFrame with columns ``variant_id``, ``tsne_x``, ``tsne_y``.
    """
    n = X.shape[0]
    if n < 3:
        return pd.DataFrame({"variant_id": X.index, "tsne_x": np.nan, "tsne_y": np.nan})

    # Clamp perplexity to valid range: must be < n
    p = min(perplexity, max(2, n - 1))
    tsne = TSNE(
        n_components=2,
        perplexity=p,
        init="pca",
        learning_rate="auto",
        random_state=seed,
    )
    coords = tsne.fit_transform(X.values)
    return pd.DataFrame({"variant_id": X.index, "tsne_x": coords[:, 0], "tsne_y": coords[:, 1]})


def make_metric_rows(
    generation_id: int,
    df_coords: pd.DataFrame,
    metric_def_ids: Dict[tuple[str, str], int],
    include_tsne: bool,
) -> List[Dict[str, Any]]:
    """Convert embedding coordinates into metric rows ready for insertion."""
    rows: List[Dict[str, Any]] = []
    for _, r in df_coords.iterrows():
        vid = int(r["variant_id"])

        rows.append({
            "generation_id": generation_id,
            "variant_id": vid,
            "wt_control_id": None,
            "metric_name": "pca_x",
            "metric_type": "derived",
            "value": float(r["pca_x"]),
            "unit": None,
            "metric_definition_id": metric_def_ids.get(("pca_x", "derived")),
        })
        rows.append({
            "generation_id": generation_id,
            "variant_id": vid,
            "wt_control_id": None,
            "metric_name": "pca_y",
            "metric_type": "derived",
            "value": float(r["pca_y"]),
            "unit": None,
            "metric_definition_id": metric_def_ids.get(("pca_y", "derived")),
        })

        if include_tsne:
            rows.append({
                "generation_id": generation_id,
                "variant_id": vid,
                "wt_control_id": None,
                "metric_name": "tsne_x",
                "metric_type": "derived",
                "value": float(r["tsne_x"]),
                "unit": None,
                "metric_definition_id": metric_def_ids.get(("tsne_x", "derived")),
            })
            rows.append({
                "generation_id": generation_id,
                "variant_id": vid,
                "wt_control_id": None,
                "metric_name": "tsne_y",
                "metric_type": "derived",
                "value": float(r["tsne_y"]),
                "unit": None,
                "metric_definition_id": metric_def_ids.get(("tsne_y", "derived")),
            })

    return rows


def precompute_embeddings_for_generation(
    generation_id: int,
    include_tsne: bool = False,
    seed: int = 42,
    perplexity: int = 30,
    refresh_view: bool = False,
) -> None:
    """
    Builds mutation vectors, runs PCA (and optionally t-SNE),
    then upserts the coordinates as derived metrics.
    """
    with db_conn() as conn:
        variants, muts = fetch_variants_and_mutations(conn, generation_id)
        if variants.empty:
            raise RuntimeError(f"No variants found for generation_id={generation_id}")

        # Build binary mutation feature matrix for dimensionality reduction
        X = build_mutation_matrix(muts)

        all_vids = variants["variant_id"].astype(int).tolist()

        # When no protein mutations exist, assign zero coordinates
        if X.empty:
            coords = pd.DataFrame({"variant_id": all_vids, "pca_x": 0.0, "pca_y": 0.0})
            if include_tsne:
                coords["tsne_x"] = 0.0
                coords["tsne_y"] = 0.0
        else:
            # Ensure all variant IDs are present; missing ones get zero vectors
            X = X.reindex(all_vids, fill_value=0)
            coords = compute_pca_xy(X, seed=seed)

            if include_tsne:
                tsne_df = compute_tsne_xy(X, seed=seed, perplexity=perplexity)
                coords = coords.merge(tsne_df, on="variant_id", how="left")

        metric_def_ids = fetch_metric_definition_ids(conn, ["pca_x", "pca_y", "tsne_x", "tsne_y"])

        # Delete-then-insert pattern for idempotent upsert
        names = ["pca_x", "pca_y"] + (["tsne_x", "tsne_y"] if include_tsne else [])
        delete_metrics_by_name(conn, generation_id=generation_id, metric_names=names, metric_type="derived")

        rows = make_metric_rows(
            generation_id=generation_id,
            df_coords=coords,
            metric_def_ids=metric_def_ids,
            include_tsne=include_tsne,
        )
        bulk_insert_metrics(conn, rows)

        if refresh_view:
            refresh_materialized_view(conn, "mv_activity_landscape")


def main():
    """CLI entrypoint for precomputing and storing generation embeddings."""
    ap = argparse.ArgumentParser(description="Precompute PCA/t-SNE embeddings and store in metrics.")
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--include-tsne", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--perplexity", type=int, default=30)
    ap.add_argument("--refresh-view", action="store_true")
    args = ap.parse_args()

    precompute_embeddings_for_generation(
        generation_id=args.generation_id,
        include_tsne=args.include_tsne,
        seed=args.seed,
        perplexity=args.perplexity,
        refresh_view=args.refresh_view,
    )

    print(f"Done. Stored embeddings for generation_id={args.generation_id} (tsne={args.include_tsne}).")


if __name__ == "__main__":
    main()
