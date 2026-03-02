"""Query helpers that feed the analysis views and exported reports."""

from __future__ import annotations
from typing import Dict, Tuple
import pandas as pd

import warnings
warnings.filterwarnings(
    "ignore",
    message="pandas only supports SQLAlchemy connectable",
    category=UserWarning,
)

LATEST_ACTIVITY_SCORE_SQL = """
SELECT
  m.variant_id,
  m.value AS activity_score
FROM metrics m
JOIN (
  SELECT variant_id, MAX(metric_id) AS metric_id
  FROM metrics
  WHERE metric_name = 'activity_score'
    AND metric_type = 'derived'
  GROUP BY variant_id
) latest ON latest.metric_id = m.metric_id
"""

LATEST_MUTATION_TOTAL_SQL = """
SELECT
  m.variant_id,
  m.value AS total_mutations
FROM metrics m
JOIN (
  SELECT variant_id, MAX(metric_id) AS metric_id
  FROM metrics
  WHERE metric_name = 'mutation_total_count'
    AND metric_type = 'derived'
  GROUP BY variant_id
) latest ON latest.metric_id = m.metric_id
"""

WT_BASELINE_SQL = """
SELECT
  m.generation_id,
  AVG(CASE WHEN m.metric_name IN ('dna_yield_raw', 'dna_yield') THEN m.value END)     AS dna_wt,
  AVG(CASE WHEN m.metric_name IN ('protein_yield_raw', 'protein_yield') THEN m.value END) AS prot_wt
FROM metrics m
WHERE m.wt_control_id IS NOT NULL
  AND m.metric_type='raw'
  AND m.metric_name IN ('dna_yield_raw', 'protein_yield_raw', 'dna_yield', 'protein_yield')
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
  MAX(CASE WHEN m.metric_name IN ('dna_yield_raw', 'dna_yield') THEN m.value END)      AS dna_yield_raw,
  MAX(CASE WHEN m.metric_name IN ('protein_yield_raw', 'protein_yield') THEN m.value END)  AS protein_yield_raw
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
LEFT JOIN metrics m
  ON m.variant_id = v.variant_id
 AND m.metric_type = 'raw'
 AND m.metric_name IN ('dna_yield_raw', 'protein_yield_raw', 'dna_yield', 'protein_yield')
WHERE g.experiment_id = %s
GROUP BY v.variant_id, v.generation_id, g.generation_number, v.plasmid_variant_index
ORDER BY g.generation_number, v.plasmid_variant_index;
"""

TOP10_SQL = f"""
SELECT
  v.variant_id,
  g.generation_number,
  v.plasmid_variant_index,
  act.activity_score,
  COALESCE(
    mt.total_mutations,
    CAST(NULLIF(v.extra_metadata->'sequence_analysis'->'mutation_counts'->>'total', '') AS integer),
    tm.total_mut_count,
    0
  )::int AS total_mutations
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
JOIN (
  {LATEST_ACTIVITY_SCORE_SQL}
) act ON act.variant_id = v.variant_id
LEFT JOIN (
  {LATEST_MUTATION_TOTAL_SQL}
) mt ON mt.variant_id = v.variant_id
LEFT JOIN (
  SELECT variant_id, COUNT(*) AS total_mut_count
  FROM mutations
  GROUP BY variant_id
) tm ON tm.variant_id = v.variant_id
WHERE g.experiment_id = %s
ORDER BY act.activity_score DESC
LIMIT 10;
"""

DISTRIBUTION_SQL = f"""
SELECT
  g.generation_number,
  act.activity_score
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
JOIN (
  {LATEST_ACTIVITY_SCORE_SQL}
) act ON act.variant_id = v.variant_id
WHERE g.experiment_id = %s
ORDER BY g.generation_number;
"""

PROTEIN_SIMILARITY_NODES_SQL = f"""
WITH scores AS (
  SELECT
    v.variant_id,
    g.experiment_id,
    act.activity_score
  FROM variants v
  JOIN generations g ON g.generation_id = v.generation_id
  LEFT JOIN (
    {LATEST_ACTIVITY_SCORE_SQL}
  ) act ON act.variant_id = v.variant_id
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
  v.protein_sequence,
  g.generation_number,
  v.plasmid_variant_index,
  r.activity_score,
  -- Top-10 is a highlight flag for plots; it is not a hard filter on returned rows.
  CASE WHEN r.rn <= 10 AND r.activity_score IS NOT NULL THEN 1 ELSE 0 END AS is_top10
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
LEFT JOIN ranked r ON r.variant_id = v.variant_id
WHERE g.experiment_id = %s;
"""

PROTEIN_MUTATIONS_SQL = """
SELECT
  v.variant_id,
  m.position,
  m.original,
  m.mutated
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
JOIN mutations m ON m.variant_id = v.variant_id
WHERE g.experiment_id = %s
  AND m.mutation_type = 'protein';
"""

LINEAGE_NODES_SQL = f"""
WITH scores AS (
  SELECT
    v.variant_id,
    g.experiment_id,
    act.activity_score
  FROM variants v
  JOIN generations g ON g.generation_id = v.generation_id
  LEFT JOIN (
    {LATEST_ACTIVITY_SCORE_SQL}
  ) act ON act.variant_id = v.variant_id
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
ORDER BY
  g.generation_number,
  CASE WHEN v.plasmid_variant_index ~ '^[0-9]+$' THEN v.plasmid_variant_index::int ELSE NULL END,
  v.plasmid_variant_index;
"""


LINEAGE_EDGES_SQL = """
SELECT
  v.parent_variant_id AS parent_id,
  v.variant_id AS child_id
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
JOIN variants p ON p.variant_id = v.parent_variant_id
JOIN generations gp ON gp.generation_id = p.generation_id
WHERE g.experiment_id = %s
  AND v.parent_variant_id IS NOT NULL
  AND gp.experiment_id = %s;
"""

EXPERIMENT_IDS_SQL = """
SELECT experiment_id
FROM experiments
ORDER BY experiment_id;
"""


def fetch_wt_baselines(conn, experiment_id: int) -> Dict[int, Tuple[float, float]]:
    """Return strict per-generation WT baselines for Stage 4 normalization."""
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

    # STRICT check: enforce one usable WT baseline per generation to keep normalization comparable.
    df_generations = pd.read_sql(
        """
        SELECT generation_id, generation_number
        FROM generations
        WHERE experiment_id = %s
        ORDER BY generation_number;
        """,
        conn,
        params=(experiment_id,),
    )
    expected = set(df_generations["generation_id"].astype(int).tolist())
    missing_ids = sorted(expected - set(baselines.keys()))
    if missing_ids:
        missing_map = (
            df_generations[df_generations["generation_id"].isin(missing_ids)]
            .set_index("generation_id")["generation_number"]
            .to_dict()
        )
        missing_gen_nums = [int(missing_map[g]) for g in missing_ids]
        raise ValueError(
            f"Missing WT baselines for experiment {experiment_id} generations: "
            f"{missing_gen_nums}. Stage 4 normalisation cannot proceed."
        )

    return baselines

def fetch_variant_raw(conn, experiment_id: int) -> pd.DataFrame:
    """Load raw DNA and protein yields for every variant in the experiment."""
    return pd.read_sql(VARIANT_RAW_SQL, conn, params=(experiment_id,))

def fetch_top10(conn, experiment_id: int) -> pd.DataFrame:
    """Return the latest top-ten ranking by derived activity score."""
    return pd.read_sql(TOP10_SQL, conn, params=(experiment_id,))

def fetch_distribution(conn, experiment_id: int) -> pd.DataFrame:
    """Return activity-score values grouped by generation for plotting."""
    return pd.read_sql(DISTRIBUTION_SQL, conn, params=(experiment_id,))

def fetch_protein_similarity_nodes(conn, experiment_id: int) -> pd.DataFrame:
    """Load protein-network nodes and ranking metadata for one experiment."""
    # The same experiment id is used twice because the SQL has two placeholders.
    return pd.read_sql(PROTEIN_SIMILARITY_NODES_SQL, conn, params=(experiment_id, experiment_id))

def fetch_protein_mutations(conn, experiment_id: int) -> pd.DataFrame:
    """Return stored protein mutation rows for network co-occurrence mode."""
    return pd.read_sql(PROTEIN_MUTATIONS_SQL, conn, params=(experiment_id,))

def fetch_lineage_nodes(conn, experiment_id: int) -> pd.DataFrame:
    """Load the variant nodes shown in the experiment-local lineage chart."""
    q = f"""
    SELECT
      v.variant_id,
      g.generation_number,
      v.plasmid_variant_index,
      act.activity_score,
      COALESCE(
        mt.total_mutations,
        CAST(NULLIF(v.extra_metadata->'sequence_analysis'->'mutation_counts'->>'total', '') AS integer),
        pm.protein_mutations,
        0
      )::int AS total_mutations
    FROM variants v
    JOIN generations g ON g.generation_id = v.generation_id
    LEFT JOIN (
      {LATEST_MUTATION_TOTAL_SQL}
    ) mt ON mt.variant_id = v.variant_id
    LEFT JOIN (
      SELECT variant_id, COUNT(*) AS protein_mutations
      FROM mutations
      WHERE mutation_type = 'protein'
      GROUP BY variant_id
    ) pm ON pm.variant_id = v.variant_id
    LEFT JOIN (
      {LATEST_ACTIVITY_SCORE_SQL}
    ) act ON act.variant_id = v.variant_id
    WHERE g.experiment_id = %s;
    """
    return pd.read_sql(q, conn, params=(experiment_id,))

def fetch_lineage_edges(conn, experiment_id: int) -> pd.DataFrame:
    """Return lineage edges for the experiment-local lineage chart."""
    return pd.read_sql(LINEAGE_EDGES_SQL, conn, params=(experiment_id, experiment_id))

def fetch_experiment_ids(conn) -> list[int]:
    """List every experiment id available for static generation jobs."""
    df = pd.read_sql(EXPERIMENT_IDS_SQL, conn)
    return [int(x) for x in df["experiment_id"].tolist()]
