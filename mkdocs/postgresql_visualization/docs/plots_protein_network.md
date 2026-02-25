# Protein network

## Data sources
- Sequence identity mode: `variants.protein_sequence` + `metrics.activity_score`
- Mutation co-occurrence mode: `mutations` (protein) + `metrics.activity_score`

## Tunable parameters
- Identity threshold
- Minimum shared mutations
- Optional Jaccard threshold

## Endpoint
`/protein_similarity/<experiment_id>`

Examples:
- `/protein_similarity/41?mode=identity&identity_threshold=0.95`
- `/protein_similarity/41?mode=cooccurrence&min_shared=2&jaccard_threshold=0.10`
- `/protein_similarity/41?mode=identity&preset=sparse`

## Presets
- `sparse`: fewer edges, stronger similarity
- `medium`: balanced density
- `dense`: more edges, exploratory view

## SQL checks
```sql
-- identity mode readiness
select count(*) as n_with_sequence
from variants v
join generations g on g.generation_id = v.generation_id
where g.experiment_id = 41
  and v.protein_sequence is not null;

-- co-occurrence mode readiness
select count(*) as n_protein_mutations
from mutations m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where g.experiment_id = 41
  and m.mutation_type='protein';
```

## Interpretation
- Identity mode links sequence-similar variants.
- Co-occurrence mode links variants sharing amino-acid substitutions.
- Top-scoring nodes are emphasized for quick visual ranking context.

## Example graph
![Protein network example](assets/plots/protein_network_placeholder.svg)

Replace this placeholder by generating a protein network PNG and saving it in `mkdocs/postgresql_visualization/docs/assets/plots/`.
