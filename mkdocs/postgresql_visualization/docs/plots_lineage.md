# Lineage plot

## Data sources
- Nodes and parent relationships: `variants`, `generations`
- Optional lineage acceleration: `variant_lineage_closure`
- Optional mutation context: `mutations`

## Suggested inputs
- `experiment_id` for the route
- parent-child links (`parent_variant_id`)
- generation number for layered plotting

## Endpoint
`/lineage/<experiment_id>`

Example:
`/lineage/41`

## SQL check
```sql
select
  v.parent_variant_id as parent_id,
  v.variant_id as child_id,
  g.generation_number
from variants v
join generations g on g.generation_id = v.generation_id
where g.experiment_id = 41
  and v.parent_variant_id is not null
order by g.generation_number;
```

## Interpretation
- Left-to-right progression follows generation number.
- Edges represent parent-child inheritance between variants.
- Isolated nodes can indicate missing parent assignments in loaded data.

## Example graph
![Lineage example](assets/plots/lineage_exp41.png)
