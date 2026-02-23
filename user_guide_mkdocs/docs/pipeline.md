# Pipelines

## Rankings and mutation introductions
- Compute top-10 variants per generation by activity score.
- Trace lineage to record the first appearance of each mutation.

### Recommended cadence
- Recompute after new metrics are loaded
- Recompute if lineage is backfilled

## Embeddings (PCA)
- Build feature vectors from protein mutation positions per variant.
- Run PCA for 2D coordinates.
- Store results in `embedding_runs` and `embedding_points`.

### Inputs
- Variants with `activity_score`
- Protein mutation positions

## Refresh
After any pipeline run, refresh materialized views:

```sql
select refresh_bonus_materialized_views();
```

## Validation checks
- `embedding_points` row count should match variants with `activity_score`
- `mv_activity_landscape` row count should match `embedding_points`
