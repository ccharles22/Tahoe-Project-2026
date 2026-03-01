# Top 10 table

The Top 10 table ranks the highest-performing variants in the selected
experiment using the unified activity score.

## What it shows

Each row combines:

- generation number
- plasmid variant index
- unified `activity_score`
- total mutation count relative to the WT reference

This creates a compact experiment-level ranking view rather than a
generation-by-generation ranking.

## Data sources

- Activity scores: latest `metrics` rows where
  `metric_name='activity_score'` and `metric_type='derived'`
- Mutation totals: `metrics.mutation_total_count` when present, with fallbacks
  to stored sequence-analysis totals and finally raw mutation-row counts
- Generation and variant labels: `generations`, `variants`

## Endpoint

`/top10/<experiment_id>`

Example:

`/top10/41`

## SQL check

```sql
select
  g.generation_number,
  v.plasmid_variant_index,
  m.value as activity_score
from metrics m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where m.metric_name = 'activity_score'
  and m.metric_type = 'derived'
  and g.experiment_id = 41
order by m.metric_id desc, m.value desc
limit 10;
```

## Interpretation

- Rows are the highest `activity_score` variants across the full experiment.
- High rank does not necessarily imply low mutation burden; late-generation,
  high-performing variants may also carry many cumulative mutations.
- Comparing activity score and mutation count together helps distinguish:
  - strong performance with modest sequence drift
  - strong performance after extensive divergence from WT
- In the interactive workspace view, the `View` action exposes per-variant
  sequence and mutation details, which is useful for validating whether a
  top-ranked variant is biologically plausible.

If fewer than 10 rows appear, not enough valid derived activity scores were
written for that experiment.

## Example graph

![Top 10 example](assets/plots/top10_exp41.png)
