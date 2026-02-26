# Metrics

This section describes how metrics are stored, typed, and updated in the project.

## Metric categories

- `raw`: direct measured values (for example `dna_yield_raw`, `protein_yield_raw`)
- `normalized`: scaled values (`dna_yield_norm`, `protein_yield_norm`)
- `derived`: computed outputs (mainly `activity_score`)

## Unified metrics strategy

The metric flow described in the tutorials is:
1. Store raw DNA/protein yields.
2. Compute WT baseline values per generation.
3. Normalize variant values against WT.
4. Compute final `activity_score` from normalized ratios.
5. Store both normalized and derived outputs for downstream ranking/plots.

This supports top-variant selection and generation-level activity distribution views.

## Current scoring policy

- Report generation uses WT-based normalization only.
- If WT baselines are missing or invalid, score computation fails with an explicit error.
- No median-based fallback is used in current pipeline runs.

## Where metrics live

- Table: `metrics`
- Optional dictionary table: `metric_definitions`

`metrics` rows are attached to either:
- a variant (`variant_id`), or
- a WT control (`wt_control_id`)

## Key storage behavior

- `generation_id` is automatically set by trigger logic from `variant_id` or `wt_control_id`.
- Uniqueness is enforced so one `(generation_id, variant_id, metric_name, metric_type)` row exists per variant metric.
- WT rows use analogous uniqueness with `wt_control_id`.

## Upsert logic used by code

Code path:
- `src/analysis_MPL/metrics.py` -> `upsert_variant_metrics`

Behavior:
- Inserts metric rows.
- On conflict, updates `value` and `unit`.

## Common metric names in this repo

- `dna_yield_raw`
- `protein_yield_raw`
- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`

For detailed formulas and QC exclusions, see:
- [Activity score calculations](activity_score_calculations.md)

## Quick validation SQL

```sql
-- all activity scores
select count(*) as n_activity_scores
from metrics
where metric_name = 'activity_score'
  and metric_type = 'derived';

-- count by metric name + type
select metric_name, metric_type, count(*) as n
from metrics
group by metric_name, metric_type
order by metric_name, metric_type;
```
