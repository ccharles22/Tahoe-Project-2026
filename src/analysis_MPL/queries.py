from __future__ import annotations
from typing import Dict, Tuple
import pandas as pd

import warnings
warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable",
    category=UserWarning,
)

WT_BASELINE_SQL = """
SELECT
  m.generation_id,
  AVG(CASE WHEN m.metric_name='dna_yield_raw' THEN m.value END)     AS dna_wt,
  AVG(CASE WHEN m.metric_name='protein_yield_raw' THEN m.value END) AS prot_wt
FROM metrics m
WHERE m.wt_control_id IS NOT NULL
  AND m.metric_type='raw'
  AND m.metric_name IN ('dna_yield_raw','protein_yield_raw')
  AND m.generation_id IN (
    SELECT g.generation_id
    FROM generations g
    WHERE g.experiment_id = %s
  )
GROUP BY m.generation_id;
"""

VARIANT_RAW_SQL = """
SELECT
  v.variant_id,
  v.generation_id,
  g.generation_number,
  v.plasmid_variant_index,
  MAX(CASE WHEN m.metric_name='dna_yield' THEN m.value END)      AS dna_yield_raw,
  MAX(CASE WHEN m.metric_name='protein_yield' THEN m.value END)  AS protein_yield_raw
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
LEFT JOIN metrics m
  ON m.variant_id = v.variant_id
 AND m.metric_type = 'raw'
 AND m.metric_name IN ('dna_yield','protein_yield')
WHERE g.experiment_id = %s
GROUP BY v.variant_id, v.generation_id, g.generation_number, v.plasmid_variant_index
ORDER BY g.generation_number, v.plasmid_variant_index;
"""

TOP10_SQL = """
SELECT
  g.generation_number,
  v.plasmid_variant_index,
  m.value AS activity_score,
  COALESCE(pm.protein_mut_count, 0) AS protein_mutations
FROM metrics m
JOIN variants v ON v.variant_id = m.variant_id
JOIN generations g ON g.generation_id = v.generation_id
LEFT JOIN (
  SELECT variant_id, COUNT(*) AS protein_mut_count
  FROM mutations
  WHERE mutation_type='protein'
  GROUP BY variant_id
) pm ON pm.variant_id = v.variant_id
WHERE m.metric_name='activity_score'
  AND m.metric_type='derived'
  AND g.experiment_id = %s
ORDER BY m.value DESC
LIMIT 10;
"""

DISTRIBUTION_SQL = """
SELECT
  g.generation_number,
  m.value AS activity_score
FROM metrics m
JOIN variants v ON v.variant_id = m.variant_id
JOIN generations g ON g.generation_id = v.generation_id
WHERE m.metric_name='activity_score'
  AND m.metric_type='derived'
  AND g.experiment_id = %s
ORDER BY g.generation_number;
"""

LINEAGE_NODES_SQL = """
WITH scores AS (
  SELECT
    v.variant_id,
    g.experiment_id,
    m.value AS activity_score
  FROM variants v
  JOIN generations g ON g.generation_id = v.generation_id
  LEFT JOIN metrics m
    ON m.variant_id = v.variant_id
   AND m.metric_name = 'activity_score'
   AND m.metric_type = 'derived'
  WHERE g.experiment_id = %s
),
ranked AS (
  SELECT
    variant_id,
    activity_score,
    ROW_NUMBER() OVER (
      ORDER BY activity_score DESC NULLS LAST
    ) AS rn
  FROM scores
)
SELECT
  v.variant_id,
  v.parent_variant_id,
  v.generation_id,
  g.generation_number,
  v.plasmid_variant_index,
  r.activity_score,
  CASE WHEN r.rn <= 10 AND r.activity_score IS NOT NULL THEN 1 ELSE 0 END AS is_top10
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
LEFT JOIN ranked r ON r.variant_id = v.variant_id
WHERE g.experiment_id = %s
ORDER BY g.generation_number, v.plasmid_variant_index;
"""


LINEAGE_EDGES_SQL = """
SELECT
  child.variant_id  AS child_id,
  child.parent_variant_id AS parent_id
FROM variants child
JOIN generations g ON g.generation_id = child.generation_id
WHERE g.experiment_id = %s
  AND child.parent_variant_id IS NOT NULL;
"""

EXPERIMENT_IDS_SQL = """
SELECT experiment_id
FROM experiments
ORDER BY experiment_id;
"""


def fetch_wt_baselines(conn, experiment_id: int) -> Dict[int, Tuple[float, float]]:
    df = pd.read_sql(WT_BASELINE_SQL, conn, params=(experiment_id,))
    baselines: Dict[int, Tuple[float, float]] = {}

    for _, row in df.iterrows():
        dna = row["dna_wt"]
        prot = row["prot_wt"]

        # Skip generations where WT baseline is incomplete
        if pd.isna(dna) or pd.isna(prot):
            continue

        baselines[int(row["generation_id"])] = (float(dna), float(prot))

    # STRICT check: stop analysis if no valid baselines exist
    if not baselines:
        raise ValueError(
            f"No valid WT baselines found for experiment {experiment_id}. "
            "Stage 4 normalisation cannot proceed."
        )

    return baselines

def fetch_variant_raw(conn, experiment_id: int) -> pd.DataFrame:
    return pd.read_sql(VARIANT_RAW_SQL, conn, params=(experiment_id,))

def fetch_top10(conn, experiment_id: int) -> pd.DataFrame:
    return pd.read_sql(TOP10_SQL, conn, params=(experiment_id,))

def fetch_distribution(conn, experiment_id: int) -> pd.DataFrame:
    return pd.read_sql(DISTRIBUTION_SQL, conn, params=(experiment_id,))

def fetch_lineage_nodes(conn, experiment_id: int) -> pd.DataFrame:
    return pd.read_sql(LINEAGE_NODES_SQL, conn, params=(experiment_id, experiment_id))

def fetch_lineage_edges(conn, experiment_id: int) -> pd.DataFrame:
    return pd.read_sql(LINEAGE_EDGES_SQL, conn, params=(experiment_id,))

def fetch_experiment_ids(conn) -> list[int]:
    df = pd.read_sql(EXPERIMENT_IDS_SQL, conn)
    return [int(x) for x in df["experiment_id"].tolist()]