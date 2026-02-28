CREATE MATERIALIZED VIEW IF NOT EXISTS mv_domain_mutation_enrichment AS
SELECT
  v.generation_id,
  pf.wt_id,
  pf.feature_type,
  COALESCE(pf.description, pf.feature_type) AS domain_label,
  COUNT(*) FILTER (WHERE m.is_synonymous IS FALSE) AS nonsyn_count,
  COUNT(*) FILTER (WHERE m.is_synonymous IS TRUE)  AS syn_count,
  COUNT(*) AS total_protein_mutations,
  (pf.end_position - pf.start_position + 1) AS domain_length,
  COUNT(*) FILTER (WHERE m.is_synonymous IS FALSE)::float
    / NULLIF((pf.end_position - pf.start_position + 1), 0) AS nonsyn_per_residue
FROM variants v
JOIN mutations m
  ON m.variant_id = v.variant_id
 AND m.mutation_type = 'protein'
JOIN protein_features pf
  ON m.position BETWEEN pf.start_position AND pf.end_position

GROUP BY
  v.generation_id, pf.wt_id,pf.feature_type, domain_label, pf.start_position, pf.end_position
;
