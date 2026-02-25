# Top 10 table

## Data sources
- Activity scores: `metrics` where `metric_name='activity_score'` and `metric_type='derived'`
- Mutation counts: `mutations` (protein)
- Generation + variant labels: `generations`, `variants`

## Suggested filters
- Filter by `experiment_id`

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
where m.metric_name='activity_score'
  and m.metric_type='derived'
  and g.experiment_id = 41
order by m.value desc
limit 10;
```

## Interpretation
- Rows are the highest `activity_score` variants in the selected experiment.
- If fewer than 10 rows appear, not enough valid derived metrics were computed.

## Example graph
![Top 10 example](assets/plots/top10_exp41.png)
