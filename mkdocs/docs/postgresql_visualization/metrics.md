# Metrics Overview

This section explains how the platform stores, classifies, and reuses metrics
across sequence analysis, ranking, and reporting.

## Metric categories

The project uses three main metric classes:

- `raw`: direct measured values, such as `dna_yield_raw` and
  `protein_yield_raw`
- `normalized`: values scaled against a baseline, such as `dna_yield_norm` and
  `protein_yield_norm`
- `derived`: computed outputs, primarily `activity_score`

## Metric flow

The high-level metric flow is:

1. Store raw DNA and protein yields
2. Establish the generation-specific WT baseline
3. Normalize variant values against that baseline
4. Compute the final `activity_score`
5. Persist normalized and derived values for downstream ranking and plotting

This is what allows the application to compare variants consistently within an
experiment.

## What this section covers

Use the pages in this group for:

- **Storage & Types**: where metrics live and how they are written
- **Activity Score Calculations**: the actual normalization and formula logic
- **QC & Validation**: what is excluded, and how to verify the output rows

## Common metric names

- `dna_yield_raw`
- `protein_yield_raw`
- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`

## Related pages

- [Metric Storage & Types](metric_storage_and_types.md)
- [Activity Score Calculations](activity_score_calculations.md)
- [Metric QC & Validation](metric_qc_and_validation.md)
