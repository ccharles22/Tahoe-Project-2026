# Lineage plot

The lineage visualisation shows the evolutionary relationships between variants
within the selected experiment.

## Data sources

- Nodes and parent relationships: `variants`, `generations`
- Optional lineage acceleration: `variant_lineage_closure`
- Optional mutation context: `mutations`

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
- Directed edges represent parent-child inheritance between variants.
- Branching patterns highlight where one variant gave rise to multiple
  descendants.
- Dense successful branches can indicate an adaptive lineage that continued to
  diversify while retaining useful sequence features.
- Isolated nodes are expected for roots of the local experiment view, but they
  can also indicate missing `parent_variant_id` values in loaded data.

This view is especially useful when cross-checking Top 10 results, because it
shows whether the best-performing variants come from one dominant lineage or
from multiple independent branches.

## Example graph

![Lineage example](assets/plots/lineage_exp41.png)
