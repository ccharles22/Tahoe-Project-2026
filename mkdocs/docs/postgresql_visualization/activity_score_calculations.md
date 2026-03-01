# Activity Score Calculations

This page explains the core formula used to compute `activity_score` and how
that value should be interpreted.

## Core concept

The activity score compares each variant against the wild-type baseline of the
same generation.

At a high level:

- `dna_yield_norm = dna_yield_raw / dna_wt`
- `protein_yield_norm = protein_yield_raw / protein_wt`
- `activity_score = dna_yield_norm / protein_yield_norm`

This produces a single relative metric that can be used for ranking and
distribution views.

## Inputs

The calculation depends on:

- `dna_yield_raw`
- `protein_yield_raw`
- the generation-specific WT baseline values

Those raw measurements are stored in the `metrics` table and grouped by
generation before the final derived score is written.

## WT-based normalization

For a valid generation:

- DNA is normalized against the WT DNA baseline
- protein is normalized against the WT protein baseline
- the final score is the ratio of those two normalized values

This ensures the score reflects generation-relative performance rather than raw
absolute scale alone.

## Worked example

If a variant has:

- `dna_yield_raw = 120`
- `protein_yield_raw = 40`

And the WT baseline is:

- `dna_wt = 100`
- `protein_wt = 50`

Then:

- `dna_yield_norm = 120 / 100 = 1.2`
- `protein_yield_norm = 40 / 50 = 0.8`
- `activity_score = 1.2 / 0.8 = 1.5`

## Interpretation

- `activity_score > 1`: the DNA-normalized signal is stronger than the
  protein-normalized signal
- `activity_score < 1`: the protein-normalized signal is relatively stronger
- `activity_score ≈ 1`: the normalized behavior is balanced

These values are comparative and should be read in the context of the same
experiment and generation.

## What gets stored

When a row passes QC, the pipeline writes:

- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`

These outputs are then used by:

- Top 10 ranking
- activity distributions
- downstream visual summaries

## Related pages

- [Metrics Overview](metrics.md)
- [Metric Storage & Types](metric_storage_and_types.md)
- [Metric QC & Validation](metric_qc_and_validation.md)
