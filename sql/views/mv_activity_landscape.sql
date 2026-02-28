CREATE MATERIALIZED VIEW IF NOT EXISTS mv_activity_landscape AS
WITH act AS (
  SELECT variant_id, generation_id, value AS activity_score
  FROM metrics
  WHERE metric_name='activity_score' AND metric_type='derived' AND variant_id IS NOT NULL
),
coords AS (
  SELECT
    m.variant_id,
    m.generation_id,
    er.embedding_run_id,
    er.experiment_id,
    er.method,
    MAX(CASE WHEN m.metric_name = er.method || '_x' THEN m.value END) AS x,
    MAX(CASE WHEN m.metric_name = er.method || '_y' THEN m.value END) AS y
  FROM metrics m
  JOIN embedding_runs er ON er.generation_id = m.generation_id
  WHERE m.metric_type='derived'
    AND m.metric_name IN ('pca_x','pca_y','tsne_x','tsne_y')
  GROUP BY m.variant_id, m.generation_id, er.embedding_run_id, er.experiment_id, er.method
),
prot_mut AS (
  SELECT variant_id, COUNT(*) AS protein_mutations
  FROM mutations
  WHERE mutation_type='protein' AND is_synonymous IS FALSE
  GROUP BY variant_id
)
SELECT
  c.embedding_run_id,
  c.experiment_id,
  c.method,
  v.variant_id,
  v.generation_id,
  v.plasmid_variant_index,
  c.x, c.y,
  a.activity_score,
  COALESCE(pm.protein_mutations, 0) AS protein_mutations
FROM variants v
JOIN coords c    ON c.variant_id=v.variant_id AND c.generation_id=v.generation_id
LEFT JOIN act a  ON a.variant_id=v.variant_id AND a.generation_id=v.generation_id
LEFT JOIN prot_mut pm ON pm.variant_id=v.variant_id
;