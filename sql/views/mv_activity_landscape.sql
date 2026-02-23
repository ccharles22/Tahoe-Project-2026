CREATE MATERIALIZED VIEW IF NOT EXISTS mv_activity_landscape AS
WITH act AS (
  SELECT variant_id, generation_id, value AS activity_score
  FROM metrics
  WHERE metric_name='activity_score' AND metric_type='derived' AND variant_id IS NOT NULL
),
pca AS (
  SELECT
    variant_id,
    generation_id,
    MAX(CASE WHEN metric_name='pca_x' THEN value END) AS pca_x,
    MAX(CASE WHEN metric_name='pca_y' THEN value END) AS pca_y
  FROM metrics
  WHERE metric_type='derived' AND metric_name IN ('pca_x','pca_y')
  GROUP BY variant_id, generation_id
),
tsne AS (
  SELECT
    variant_id,
    generation_id,
    MAX(CASE WHEN metric_name='tsne_x' THEN value END) AS tsne_x,
    MAX(CASE WHEN metric_name='tsne_y' THEN value END) AS tsne_y
  FROM metrics
  WHERE metric_type='derived' AND metric_name IN ('tsne_x','tsne_y')
  GROUP BY variant_id, generation_id
),
prot_mut AS (
  SELECT variant_id, COUNT(*) AS protein_mutations
  FROM mutations
  WHERE mutation_type='protein' AND is_synonymous IS FALSE
  GROUP BY variant_id
)
SELECT
  v.variant_id,
  v.generation_id,
  v.plasmid_variant_index,
  a.activity_score,
  p.pca_x, p.pca_y,
  t.tsne_x, t.tsne_y,
  COALESCE(pm.protein_mutations, 0) AS protein_mutations
FROM variants v
LEFT JOIN act a  ON a.variant_id=v.variant_id AND a.generation_id=v.generation_id
LEFT JOIN pca p  ON p.variant_id=v.variant_id AND p.generation_id=v.generation_id
LEFT JOIN tsne t ON t.variant_id=v.variant_id AND t.generation_id=v.generation_id
LEFT JOIN prot_mut pm ON pm.variant_id=v.variant_id
;