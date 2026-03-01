# Metric QC & Validation

This page summarizes how activity-score rows are gated and how to verify that
the stored outputs look correct.

## QC exclusions

Activity-score rows are only written for variants that pass the stage-4 metric
checks.

Typical exclusion reasons include:

- missing DNA or protein raw values
- non-positive raw values
- missing WT baseline values
- invalid WT baseline values
- normalized protein values that are too small for stable division

Only rows that pass these checks are persisted as normalized and derived
metrics.

## What gets written when QC passes

For each accepted variant, the application writes:

- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`

These outputs become the basis for:

- Top 10 ranking
- activity distribution views
- downstream visual summaries

## Practical validation checks

When validating metric outputs, check:

1. that raw DNA and protein inputs exist
2. that WT baselines exist for the same generation
3. that `activity_score` rows were actually written
4. that per-generation counts look plausible

## Minimal SQL checks

```sql
select count(*) as n_activity_scores
from metrics
where metric_name = 'activity_score'
  and metric_type = 'derived';
```

```sql
select metric_name, metric_type, count(*) as n
from metrics
group by metric_name, metric_type
order by metric_name, metric_type;
```

## What to investigate if results look wrong

- no `activity_score` rows:
  - raw metrics may be missing
  - WT baselines may be missing or invalid
- unusually low row counts:
  - too many rows may be failing QC
- unexpected score ranges:
  - denominator values may be unstable
  - experiment or generation filtering may be incorrect

Use the generated analysis CSVs alongside these checks when comparing stored
metrics to the visible plots and rankings.
