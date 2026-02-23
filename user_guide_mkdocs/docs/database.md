# Database overview

This database stores proteins, variants, mutations, metrics, and lineage relationships. It also includes extra tables and materialized views used to power the bonus visualizations.

## Core tables
- `users`, `wild_type_proteins`, `protein_features`
- `experiments`, `generations`, `variants`, `mutations`
- `metrics`, `experiment_metadata`

## Key relationships
- `experiments` -> `generations` -> `variants`
- `variants` -> `mutations` (DNA and protein)
- `metrics` records per-variant or WT control values
- `protein_features` defines domain ranges for enrichment

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
