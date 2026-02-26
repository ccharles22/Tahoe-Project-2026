# Database overview

This database stores proteins, variants, mutations, metrics, and lineage relationships. It also includes extra tables and materialized views used to power the bonus visualizations.

## Core tables
- `users`, `wild_type_proteins`, `protein_features`
- `experiments`, `generations`, `variants`, `mutations`
- `metrics`, `experiment_metadata`

## Entity flow
The main directional path for analysis is:
`experiments -> generations -> variants -> metrics/mutations`

This is the path most report and plot queries follow.

## Key relationships
- `experiments` -> `generations` -> `variants`
- `variants` -> `mutations` (DNA and protein)
- `metrics` records per-variant or WT control values
- `protein_features` defines domain ranges for enrichment

## Metrics model (important)
- Raw metrics are stored with `metric_type='raw'`
- Normalized metrics use `metric_type='normalized'`
- Final activity scoring uses `metric_type='derived'` and `metric_name='activity_score'`

At insert time, trigger logic derives `generation_id` for `metrics` rows from either:
- `variant_id`, or
- `wt_control_id`

## Lineage and analysis tables
- `variant_lineage_closure`
- `variant_sequence_analysis`

## Bonus visualization tables
- `variant_performance_rankings`: top variants per generation
- `mutation_introduction_events`: first-generation mutation appearances
- `embedding_runs` and `embedding_points`: 2D coordinates for landscapes

## Materialized view keys
- `mv_activity_landscape` is unique by `(embedding_run_id, variant_id)`
- `mv_domain_mutation_enrichment` is unique by `(generation_id, wt_id, feature_type, start_position, end_position)`

## Materialized views
- `mv_activity_landscape`: denormalized 3D landscape data
- `mv_domain_mutation_enrichment`: mutation density by protein domain

## Refresh helper
Run `select refresh_bonus_materialized_views();` after loading new embeddings or mutation data.

## Minimal validation SQL
Use these checks after loading data:

```sql
-- activity score availability
select count(*) as n_activity_scores
from metrics
where metric_name='activity_score'
  and metric_type='derived';

-- lineage closure sanity
select count(*) as n_closure_rows
from variant_lineage_closure;

-- embedding and landscape consistency
select count(*) as n_embedding_points from embedding_points;
select count(*) as n_landscape_rows from mv_activity_landscape;
```

## Operational notes
- Run schema migrations from `schema/schema.sql`.
- Keep `metric_definitions` synced if you add new metric names.
- Refresh materialized views after embedding or mutation pipeline runs.
