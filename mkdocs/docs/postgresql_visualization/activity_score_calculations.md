# Activity Score Calculations

This page explains the unified activity metric used throughout the reporting and
visualisation pipeline. The goal is to reduce two raw measurements into one
comparable score that reflects functional output relative to expression.

## Core formula

The final derived metric is:

- `activity_score = dna_yield_norm / protein_yield_norm`

The normalized inputs depend on which baseline strategy is available for the
experiment.

## Preferred strategy: WT normalization

When valid wild-type (WT) controls exist for every generation, the pipeline
normalizes each variant against the WT of the same generation:

- `dna_yield_norm = dna_yield_raw / dna_wt`
- `protein_yield_norm = protein_yield_raw / protein_wt`

This is the preferred route because it removes generation-specific assay
variation while keeping the comparison tied to a real biological control.

## Fallback strategy: generation-median normalization

Real datasets may have missing or incomplete WT controls. In that case, the
report pipeline falls back to a WT-free comparison:

- `dna_yield_norm = dna_yield_raw / median_dna_yield_for_generation`
- `protein_yield_norm = protein_yield_raw / median_protein_yield_for_generation`

The same final ratio is then applied:

- `activity_score = dna_yield_norm / protein_yield_norm`

This keeps activity scores computable and comparable within the experiment even
when the WT control data is incomplete.

## Code paths used in this project

- WT-based normalization and QC:
  - `app/services/analysis/activity_score.py`
  - `compute_stage4_metrics(...)`
- Fallback median normalization:
  - `scripts/run_report.py`
  - `compute_activity_score_fallback(...)`
- Scoring mode selection (`auto`, `wt`, `fallback`):
  - `scripts/run_report.py`

## Worked example

Variant measurements:

- `dna_yield_raw = 120`
- `protein_yield_raw = 40`

### Case 1: WT normalization available

WT baseline for the same generation:

- `dna_wt = 100`
- `protein_wt = 50`

Then:

- `dna_yield_norm = 120 / 100 = 1.20`
- `protein_yield_norm = 40 / 50 = 0.80`
- `activity_score = 1.20 / 0.80 = 1.50`

Interpretation: the variant shows roughly 50% stronger functional output
relative to its expression than the WT baseline.

### Case 2: generation-median fallback

If WT controls are unavailable, assume the generation medians are:

- `dna_median = 90`
- `protein_median = 45`

Then:

- `dna_yield_norm = 120 / 90 = 1.33`
- `protein_yield_norm = 40 / 45 = 0.89`
- `activity_score = 1.33 / 0.89 ≈ 1.49`

This produces a comparable estimate while remaining robust to missing control
rows.

## Interpretation guide

- `activity_score > 1`: improved functional efficiency relative to the chosen
  baseline
- `activity_score ≈ 1`: performance near the normalization baseline
- `activity_score < 1`: reduced efficiency relative to the baseline

These values should always be interpreted within the same experiment context,
because the normalization strategy is applied per generation.

## What gets stored

When a variant passes metric QC, the pipeline writes:

- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`

All three are stored as ratio-style outputs and then reused by:

- Top 10 ranking across the experiment
- activity score distribution plots
- downstream report summaries and bonus analyses

## Related pages

- [Metrics Overview](metrics.md)
- [Metric Storage & Types](metric_storage_and_types.md)
- [Metric QC & Validation](metric_qc_and_validation.md)
