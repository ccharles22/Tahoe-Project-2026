from __future__ import annotations

import json
from typing import Dict, List, Tuple

import os
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.analysis_MPL.database import get_conn, get_cursor


def fetch_experiment_ids(conn) -> List[int]:
    with get_cursor(conn) as cur:
        cur.execute(
            """
            select distinct g.experiment_id
            from generations g
            join variants v on v.generation_id = g.generation_id
            join metrics m on m.variant_id = v.variant_id
            where m.metric_name = 'activity_score'
              and m.metric_type = 'derived'
            order by g.experiment_id
            """
        )
        return [row["experiment_id"] for row in cur.fetchall()]


def fetch_variants_for_experiment(conn, experiment_id: int) -> pd.DataFrame:
    with get_cursor(conn) as cur:
        cur.execute(
            """
            select v.variant_id, v.generation_id, m.value as activity_score
            from variants v
            join generations g on g.generation_id = v.generation_id
            join metrics m on m.variant_id = v.variant_id
            where g.experiment_id = %s
              and m.metric_name = 'activity_score'
              and m.metric_type = 'derived'
            order by v.variant_id
            """,
            (experiment_id,),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows)


def fetch_mutation_position_range(conn, variant_ids: List[int]) -> Tuple[int, int]:
    if not variant_ids:
        return (0, -1)
    with get_cursor(conn) as cur:
        cur.execute(
            """
            with selected as (
                select unnest(%s::bigint[]) as variant_id
            )
            select min(m.position) as min_pos,
                   max(m.position) as max_pos
            from mutations m
            join selected s on s.variant_id = m.variant_id
            where m.mutation_type = 'protein'
            """,
            (variant_ids,),
        )
        row = cur.fetchone()
    if not row or row["min_pos"] is None or row["max_pos"] is None:
        return (0, -1)
    return int(row["min_pos"]), int(row["max_pos"])


def fetch_mutation_counts(conn, variant_ids: List[int]) -> pd.DataFrame:
    if not variant_ids:
        return pd.DataFrame(columns=["variant_id", "position", "cnt"])
    with get_cursor(conn) as cur:
        cur.execute(
            """
            with selected as (
                select unnest(%s::bigint[]) as variant_id
            )
            select m.variant_id,
                   m.position,
                   count(*) as cnt
            from mutations m
            join selected s on s.variant_id = m.variant_id
            where m.mutation_type = 'protein'
            group by m.variant_id, m.position
            """,
            (variant_ids,),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows)


def build_feature_matrix(
    variant_ids: List[int],
    mutations: pd.DataFrame,
    min_pos: int,
    max_pos: int,
) -> np.ndarray:
    n_variants = len(variant_ids)
    if min_pos > max_pos:
        return np.zeros((n_variants, 1), dtype=np.float32)

    n_positions = max_pos - min_pos + 1
    matrix = np.zeros((n_variants, n_positions), dtype=np.float32)
    index: Dict[int, int] = {variant_id: i for i, variant_id in enumerate(variant_ids)}

    if mutations.empty:
        return matrix

    for row in mutations.itertuples(index=False):
        variant_id = int(row.variant_id)
        if variant_id not in index:
            continue
        position = int(row.position)
        if position < min_pos or position > max_pos:
            continue
        matrix[index[variant_id], position - min_pos] = float(row.cnt)

    return matrix


def compute_pca_2d(matrix: np.ndarray) -> np.ndarray:
    centered = matrix - matrix.mean(axis=0, keepdims=True)
    u, s, _ = np.linalg.svd(centered, full_matrices=False)
    coords = np.zeros((matrix.shape[0], 2), dtype=np.float64)
    components = min(2, s.shape[0])
    if components > 0:
        coords[:, :components] = u[:, :components] * s[:components]
    return coords


def upsert_embedding_run(conn, experiment_id: int, params: dict) -> int:
    with get_cursor(conn) as cur:
        cur.execute(
            """
            delete from embedding_runs
            where experiment_id = %s
              and method = 'pca'
              and metric_name = 'activity_score'
              and metric_type = 'derived'
              and coalesce(params->>'feature', '') = %s
            returning embedding_run_id
            """,
            (experiment_id, params.get("feature", "")),
        )
        cur.fetchall()

        cur.execute(
            """
            insert into embedding_runs (experiment_id, method, metric_name, metric_type, params)
            values (%s, 'pca', 'activity_score', 'derived', %s::jsonb)
            returning embedding_run_id
            """,
            (experiment_id, json.dumps(params)),
        )
        row = cur.fetchone()
    return int(row["embedding_run_id"])


def insert_embedding_points(
    conn,
    embedding_run_id: int,
    variant_ids: List[int],
    coords: np.ndarray,
    activity_scores: np.ndarray,
) -> None:
    records = [
        (embedding_run_id, int(variant_id), float(coords[i, 0]), float(coords[i, 1]), float(activity_scores[i]))
        for i, variant_id in enumerate(variant_ids)
    ]

    with get_cursor(conn) as cur:
        cur.execute(
            """
            delete from embedding_points
            where embedding_run_id = %s
            """,
            (embedding_run_id,),
        )
        cur.executemany(
            """
            insert into embedding_points (embedding_run_id, variant_id, x, y, z)
            values (%s, %s, %s, %s, %s)
            """,
            records,
        )


def main() -> None:
    with get_conn() as conn:
        experiment_ids = fetch_experiment_ids(conn)

        for experiment_id in experiment_ids:
            variants = fetch_variants_for_experiment(conn, experiment_id)
            if variants.empty or len(variants) < 2:
                continue

            variant_ids = variants["variant_id"].astype(int).tolist()
            min_pos, max_pos = fetch_mutation_position_range(conn, variant_ids)
            mutation_counts = fetch_mutation_counts(conn, variant_ids)

            features = build_feature_matrix(variant_ids, mutation_counts, min_pos, max_pos)
            coords = compute_pca_2d(features)
            scores = variants["activity_score"].to_numpy(dtype=float)

            params = {
                "feature": "protein_mutation_counts",
                "min_position": int(min_pos),
                "max_position": int(max_pos),
                "variants": len(variant_ids),
            }

            embedding_run_id = upsert_embedding_run(conn, experiment_id, params)
            insert_embedding_points(conn, embedding_run_id, variant_ids, coords, scores)


if __name__ == "__main__":
    main()
