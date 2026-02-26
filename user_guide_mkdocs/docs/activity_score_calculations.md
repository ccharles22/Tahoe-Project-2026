# Activity Score Calculations

This page documents exactly how `activity_score` is computed, validated, stored, and interpreted in this repository.

## Unified activity metric concept

The tutorials define a unified metric that compares each variant against the WT baseline of the same generation:
- `DNA_WT_gen = mean WT DNA (raw)`
- `Protein_WT_gen = mean WT protein (raw)`
- `DNA_norm = DNA_raw_variant / DNA_WT_gen`
- `Protein_norm = Protein_raw_variant / Protein_WT_gen`
- `Activity_score = DNA_norm / Protein_norm`

This is the same approach implemented in the WT-based path below.

## Why this metric is used

`activity_score` combines DNA and protein yield behavior into one ratio:
- DNA-side signal is retained through `dna_yield_norm`.
- Protein-side signal is retained through `protein_yield_norm`.
- Dividing the two normalized values provides a single comparative score per variant.

At a high level:
- `activity_score > 1`: DNA-normalized signal is stronger than protein-normalized signal.
- `activity_score < 1`: protein-normalized signal is relatively stronger than DNA-normalized signal.
- `activity_score ~= 1`: balanced normalized behavior.

These interpretations are relative to the generation baseline used.

## Inputs

Per variant, the calculation requires:
- `dna_yield_raw`
- `protein_yield_raw`
- `generation_id`

The metrics are loaded as raw values in `metrics` with:
- `metric_name='dna_yield_raw'`
- `metric_name='protein_yield_raw'`

## Notation used in this page

- `v`: a single variant
- `g`: a single generation
- `dna_raw(v)`: raw DNA yield of variant `v`
- `prot_raw(v)`: raw protein yield of variant `v`
- `dna_wt(g)`: WT baseline DNA for generation `g`
- `prot_wt(g)`: WT baseline protein for generation `g`

## Primary method: WT-based normalization

If WT baselines exist for a generation, the pipeline uses:

- `dna_yield_norm = dna_yield_raw / dna_wt`
- `protein_yield_norm = protein_yield_raw / protein_wt`
- `activity_score = dna_yield_norm / protein_yield_norm`

Where:
- `dna_wt` = WT baseline DNA for that generation
- `protein_wt` = WT baseline protein for that generation

This logic is implemented in:
- `src/analysis_MPL/activity_score.py` (`compute_stage4_metrics`)

## Fallback method: generation-median normalization

When WT baselines are unavailable (for example synthetic datasets), fallback mode
computes activity relative to generation medians:

- `dna_yield_norm = dna_yield_raw / median(dna_yield_raw in generation)`
- `protein_yield_norm = protein_yield_raw / median(protein_yield_raw in generation)`
- `activity_score = dna_yield_norm / protein_yield_norm`

This logic is implemented in:
- `scripts/run_report.py` (`compute_activity_score_fallback`)
- `src/analysis_MPL/scoring_function_noWTcontrol.py`

### WT baseline source

WT baselines are pulled from WT control metric rows, grouped per generation:
- WT DNA baseline comes from WT DNA raw values.
- WT protein baseline comes from WT protein raw values.

If a generation has no valid WT baseline:
- `SCORING_MODE=wt` stops with an explicit error.
- `SCORING_MODE=auto` falls back to generation-median scoring.
- `SCORING_MODE=fallback` always uses generation-median scoring.

### WT-based worked example

If a variant has:
- `dna_yield_raw = 120`
- `protein_yield_raw = 40`

And the generation WT baseline is:
- `dna_wt = 100`
- `protein_wt = 50`

Then:
- `dna_yield_norm = 120 / 100 = 1.2`
- `protein_yield_norm = 40 / 50 = 0.8`
- `activity_score = 1.2 / 0.8 = 1.5`

## Full algorithm flow

1. Fetch variant-level raw metrics (`dna_yield_raw`, `protein_yield_raw`) and `generation_id`.
2. Resolve scoring mode (`auto|wt|fallback`).
3. If WT path is selected, fetch WT baselines and verify validity.
4. Otherwise, compute generation medians for fallback normalization.
5. Apply QC gates.
6. Keep only rows that pass QC.
7. Upsert three metric rows per valid variant:
   - `dna_yield_norm`
   - `protein_yield_norm`
   - `activity_score`
8. Write a stage-4 QC debug CSV for diagnostics.

## Quality control (QC) behavior

WT-based path marks rows with `qc_stage4`:
- `ok`
- `missing_raw_metrics`
- `nonpositive_raw_metrics`
- `missing_wt_baseline`
- `invalid_wt_baseline`
- `protein_norm_too_small`

Only rows with `qc_stage4='ok'` are upserted as derived metrics.

### Key QC rules
- Missing or non-positive raw values are rejected.
- Missing/invalid WT baselines are rejected in WT-based mode.
- Very small normalized protein values are rejected to avoid unstable division.

### QC warning to show in reports

When reporting activity scores, include a warning that these rows were excluded:
- missing raw values
- missing WT baseline
- baseline `<= 0`

### QC code mapping

WT-based QC (`compute_stage4_metrics`):
- `missing_raw_metrics`: DNA/protein raw value missing.
- `nonpositive_raw_metrics`: DNA/protein raw value `<= 0`.
- `missing_wt_baseline`: no WT baseline entry for generation.
- `invalid_wt_baseline`: WT baseline present but invalid (`None` or `<= 0`).
- `protein_norm_too_small`: normalized protein value too close to zero (division instability guard).
- `ok`: accepted and persisted.

## Stored output metrics

For each valid variant, the pipeline writes:
- `dna_yield_norm` (`metric_type='normalized'`)
- `protein_yield_norm` (`metric_type='normalized'`)
- `activity_score` (`metric_type='derived'`)

These are upserted into `metrics` and become the source for downstream plots and ranking.

## Database persistence details

- Upsert path: `src/analysis_MPL/metrics.py` (`upsert_variant_metrics`)
- Conflict key: `(generation_id, variant_id, metric_name, metric_type)`
- On conflict: `value` and `unit` are updated

This design allows recalculating scores safely without duplicating rows.

## Validation query

Use this query to verify derived activity metrics for one experiment:

```sql
select
  g.experiment_id,
  count(*) as activity_score_rows
from metrics m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where m.metric_name = 'activity_score'
  and m.metric_type = 'derived'
  and g.experiment_id = 41
group by g.experiment_id;
```

### Additional validation checks

```sql
-- QC distribution from generated debug CSV should align with expected exclusions.
-- Database-side sanity checks:

-- per-generation activity score counts for one experiment
select
  g.experiment_id,
  g.generation_number,
  count(*) as n_activity_scores
from metrics m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where m.metric_name = 'activity_score'
  and m.metric_type = 'derived'
  and g.experiment_id = 41
group by g.experiment_id, g.generation_number
order by g.generation_number;

-- min/max/median-like summary proxy by generation
select
  g.generation_number,
  min(m.value) as min_activity,
  max(m.value) as max_activity,
  avg(m.value) as mean_activity
from metrics m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where m.metric_name = 'activity_score'
  and m.metric_type = 'derived'
  and g.experiment_id = 41
group by g.generation_number
order by g.generation_number;
```

## Execution reminder

Run the report stage to compute and store these metrics:

```bash
export EXPERIMENT_ID=41
export SCORING_MODE=auto
python -m scripts.run_report
```

After running, inspect:
- `app/static/generated/exp_<EXPERIMENT_ID>_analysis.csv`
for per-variant QC outcomes and computed values.

## Scoring mode reminder

Use `SCORING_MODE=wt` when biological WT controls are required by your analysis.
Use `SCORING_MODE=auto` or `fallback` for synthetic/no-WT experiments.

## Practical interpretation guidance

- Compare scores within the same experiment and generation context.
- WT-based normalization is mandatory for current report runs.
- Investigate generations with unusually low accepted row counts in QC output.
- Treat scores as relative ranking signals, not absolute biophysical constants.

## Troubleshooting

- No `activity_score` rows inserted:
  - Check raw metric availability (`dna_yield_raw`, `protein_yield_raw`).
  - Check WT baseline availability/validity.
  - Review stage-4 QC CSV for exclusion reasons.
- Too many exclusions:
  - Inspect missing/nonpositive raw values.
  - Verify WT control ingestion and metric naming consistency.
- Unexpected score ranges:
  - Validate denominator behavior (`protein_yield_norm` not near zero).
  - Confirm experiment filter and generation mapping are correct.

## Supporting references

- Packer, M. S., and Liu, D. R. (2015). Methods for the directed evolution of proteins. *Nature Reviews Genetics*, 16, 379-394.
- Romero, P. A., and Arnold, F. H. (2009). Exploring protein fitness landscapes by directed evolution. *Nature Reviews Molecular Cell Biology*, 10, 866-876.
- Little, R. J. A., and Rubin, D. B. (2019). *Statistical Analysis with Missing Data* (3rd ed.). Wiley.
- Motulsky, H. (2014). *Intuitive Biostatistics* (3rd ed.). Oxford University Press.
