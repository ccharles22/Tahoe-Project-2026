# Protein network

The protein similarity network provides a structural comparison between variants
that complements the lineage view. Instead of ancestry, it emphasizes sequence
similarity or shared mutation patterns.

## Data sources

- Sequence identity mode: `variants.protein_sequence` +
  `metrics.activity_score`
- Mutation co-occurrence mode: `mutations` (protein) +
  `metrics.activity_score`

## Tunable parameters

- identity threshold
- minimum shared mutations
- optional Jaccard threshold

## Endpoint

`/protein_similarity/<experiment_id>`

Examples:

- `/protein_similarity/41?mode=identity&identity_threshold=0.95`
- `/protein_similarity/41?mode=cooccurrence&min_shared=2&jaccard_threshold=0.10`
- `/protein_similarity/41?mode=identity&preset=sparse`

## Presets

- `sparse`: fewer edges, stricter relationships
- `medium`: balanced density
- `dense`: more edges for exploratory viewing

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
  and m.mutation_type = 'protein';
```

## Interpretation

- **Identity mode** links variants with similar full-length protein sequences.
- **Co-occurrence mode** links variants that share amino-acid substitutions,
  even if they are not directly related by lineage.
- Dense clusters can indicate convergent evolution or recurring beneficial
  mutation combinations.
- Sparse isolated nodes can indicate unique mutational solutions.
- Top-scoring nodes are emphasized so the user can compare structural similarity
  against performance ranking.

This plot is best read alongside the lineage view: lineage shows ancestry, while
the protein network shows functional or mutational similarity.

## Example graph

![Protein network example](assets/plots/protein_network_placeholder.svg)

Replace this placeholder by generating a protein network PNG and saving it in
`mkdocs/postgresql_visualization/docs/assets/plots/`.
