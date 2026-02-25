# Schema design notes

This schema was created to support a directed evolution workflow from data ingestion to analysis and visualization. The work was completed in layers, starting with core entities, then adding metrics, lineage acceleration, and visualization-ready tables.

## Overview of what was done

### 1) Core data model
The foundation includes users, wild-type proteins, experiments, generations, and variants. These tables establish ownership, provenance, and the basic lineage structure. Foreign keys enforce valid relationships, and unique constraints prevent duplicate identifiers within an experiment or generation.

### 2) Sequence and mutation tracking
Variants store assembled DNA and protein sequences. Mutations are recorded in a dedicated table with type, position, and residue information. This makes mutation queries efficient and avoids repeated sequence parsing.

### 3) Metrics and normalization
A single metrics table stores raw, normalized, and derived values. Triggers populate `generation_id` and ensure metrics attach to either a variant or a wild-type control. Metric definitions provide consistent naming and units across analysis steps.

### 4) Lineage acceleration
To support fast lineage queries and network plots, a closure table stores ancestor/descendant pairs. Triggers keep this table updated when new variants are inserted and prevent re-parenting changes that would corrupt lineage.

### 5) Metadata and analysis bookkeeping
Experiment metadata and JSONB fields allow flexible, project-specific attributes without altering the schema. A sequence analysis table captures analysis status, versioning, and QC results for downstream workflows.

### 6) Visualization support
Additional tables and materialized views were introduced to serve plot-ready data:
- Per-generation rankings for top variants
- Mutation introduction events along lineages
- Embedding runs and points for the activity landscape
- Materialized views for landscape and domain enrichment summaries

## Design principles used

- Normalize the core entities for integrity, then denormalize with views for speed.
- Make biological meaning explicit (mutations, metrics, domains).
- Keep analysis outputs reproducible and query-friendly.

For full DDL details, see `schema/schema.sql` in the repository root.

## Materialized views and refresh workflow

To keep plots fast, two materialized views are built on top of the base tables:

- Activity landscape view: joins embeddings, variants, and activity metrics to provide plot-ready x/y coordinates with activity and mutation counts.
- Domain enrichment view: aggregates protein mutations by annotated feature to give per-domain densities.

These views are refreshed after loading new embeddings or mutation data using a helper refresh function. This keeps interactive plots responsive without re-running heavy joins at request time.
