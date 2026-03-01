# Metrics Overview

The platform uses a unified metric system so that raw assay values, normalized
values, and final derived scores all remain traceable to the same experiment and
generation context. This is what makes variant ranking, distribution plots, and
report generation internally consistent.

## Metric categories

Three metric classes are used throughout the pipeline:

- `raw`: direct assay measurements such as `dna_yield_raw` and
  `protein_yield_raw`
- `normalized`: baseline-scaled values such as `dna_yield_norm` and
  `protein_yield_norm`
- `derived`: higher-level outputs computed from normalized values, primarily
  `activity_score`

## Unified activity workflow

The high-level metric flow is:

1. store raw DNA and protein yields
2. attempt wild-type (WT) baseline normalization for the same generation
3. if WT baselines are unavailable, fall back to generation-median
   normalization
4. compute the final `activity_score`
5. persist normalized and derived rows for ranking, plotting, and reporting

This keeps the activity score computable even when real experimental datasets
have missing WT control measurements.

## Why this matters

Because all downstream views read from the same metric layer, the metric system
acts as the common language between:

- sequence-aware reporting
- Top 10 ranking
- activity score distributions
- lineage summaries
- protein similarity and bonus views

## What this section covers

Use the pages in this group for:

- **Metrics Overview**: the shared purpose of the metric layer
- **Metric Storage & Types**: how rows are structured and upserted
- **Activity Score Calculations**: the formula, fallback behavior, and worked
  examples
- **Metric QC & Validation**: which rows are excluded and how to check outputs

## Common metric names

- `dna_yield_raw`
- `protein_yield_raw`
- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`
- `mutation_total_count`

## Related pages

- [Metric Storage & Types](metric_storage_and_types.md)
- [Activity Score Calculations](activity_score_calculations.md)
- [Metric QC & Validation](metric_qc_and_validation.md)
