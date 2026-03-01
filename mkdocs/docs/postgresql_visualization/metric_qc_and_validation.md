# Metric QC & Validation

This page summarizes how activity-score rows are gated and how to verify that
stored outputs are scientifically plausible before you trust the rankings and
plots built from them.

## QC exclusions in WT-based scoring

WT-based activity-score rows are only written for variants that pass the stage-4
checks in `compute_stage4_metrics(...)`.

Typical exclusion reasons include:

- missing DNA or protein raw values
- non-positive raw values
- missing WT baseline values
- invalid WT baseline values
- normalized protein values that are too small for stable division

Only rows that pass these checks are persisted as normalized and derived
metrics.

## QC exclusions in fallback scoring

When the report pipeline uses generation-median normalization instead of WT
controls, rows can still be rejected if:

- the variant lacks required identifiers
- raw inputs cannot be converted to numeric values
- generation medians are undefined or zero
- the resulting normalized or derived values are non-finite

Those rows are marked as invalid fallback rows and excluded from derived output
inserts.

## What gets written when QC passes

For each accepted variant, the pipeline writes:

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
2. that WT baselines exist for the same generation, or that fallback scoring was
   intentionally used
3. that `activity_score` rows were actually written
4. that per-generation counts look plausible
5. that the top-ranked rows in the report match the highest stored activity
   scores

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

```sql
select
  g.experiment_id,
  count(*) as n_activity_scores
from metrics m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where m.metric_name = 'activity_score'
  and m.metric_type = 'derived'
group by g.experiment_id
order by g.experiment_id;
```

## What to investigate if results look wrong

- no `activity_score` rows:
  - raw metrics may be missing
  - WT baselines may be missing or invalid
  - fallback normalization may have produced invalid medians
- unusually low row counts:
  - too many rows may be failing QC
- unexpected score ranges:
  - denominator values may be unstable
  - experiment or generation filtering may be incorrect

Use the generated analysis CSVs alongside these checks when comparing stored
metrics to the visible plots and rankings.
