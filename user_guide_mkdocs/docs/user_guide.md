# User guide

This guide covers how to browse plots, run standard queries, and refresh the data products that power the visualizations.

## Who this is for
- Viewers: open the plots and understand what they show
- Analysts: pull data for ad hoc checks
- Developers: refresh pipelines and materialized views

## Plot usage (viewers)
- Lineage and mutation fingerprinting: filter by `target_variant_id` and generation
- 3D landscape: filter by `experiment_id` or `embedding_run_id`
- Domain enrichment: use `domain_label` and `nonsyn_per_residue`
- Protein network: choose sequence identity or mutation co-occurrence, then tune thresholds

### Protein network quick start
Examples:
- Identity: `/protein_similarity/1?mode=identity&identity_threshold=0.95`
- Co-occurrence: `/protein_similarity/1?mode=cooccurrence&min_shared=2&jaccard_threshold=0.1`

What to expect:
- Identity mode connects variants with high sequence identity.
- Co-occurrence mode connects variants sharing protein mutations.

## Biology background (why these plots)
### Mutation fingerprinting by generation
Directed evolution introduces mutations across generations. Tracking the first
appearance of each amino acid change along a lineage highlights when sequence
diversity emerges and which substitutions persist as the variant improves.
This supports interpretation of adaptive trajectories and helps connect
sequence changes to functional gains.
(Selles Vidal et al., 2023: https://doi.org/10.1039/D2CB00231K)

### 3D activity landscape
Protein sequences can be represented in a high-dimensional sequence space, where
distance reflects sequence dissimilarity. Dimensionality reduction (e.g., PCA)
projects this space into two coordinates for visualization while preserving
overall similarity structure. Plotting activity score on the third axis produces
an intuitive fitness landscape, where peaks represent high-activity variants.
This mirrors established approaches to visualize sequence space and identify
central or representative sequences.
(Mead et al., 2019: https://doi.org/10.1016/j.jmgm.2019.07.014)

### Domain mutation enrichment
Protein features (domains, motifs) often constrain or amplify the effects of
mutations. Aggregating nonsynonymous mutations by annotated feature highlights
regions under selection pressure, and mutation density per residue normalizes
for domain length. This helps distinguish true hotspots from long regions that
accumulate mutations by chance.

### Protein network modes
Sequence identity networks connect variants with high amino acid similarity, while
co-occurrence networks connect variants that share specific protein mutations. The
co-occurrence view emphasizes shared evolutionary steps and can be filtered with a
minimum shared-mutation count or an optional Jaccard threshold.

### Data availability for co-occurrence
Co-occurrence networks require protein mutations in the `mutations` table. If no
protein mutations were loaded or called, the co-occurrence network will be empty.

### Parameter tuning tips
- Higher identity thresholds make identity networks sparser and more conservative.
- Higher minimum shared mutation counts reduce co-occurrence density.
- Higher Jaccard thresholds favor pairs with more similar mutation sets.

### Note on normalization
When comparing quantitative protein measurements across runs or batches,
normalization helps reduce technical variation before interpreting biological
effects.
(O'Rourke et al., 2019: https://doi.org/10.3390/proteomes7030029)
(Mule et al., 2022: https://doi.org/10.1038/s41467-022-29356-8)

## Common data sources (analysts)
- Top variants: `variant_performance_rankings`
- Mutation introductions: `mutation_introduction_events`
- 3D landscape: `mv_activity_landscape`
- Domain enrichment: `mv_domain_mutation_enrichment`

## Refresh workflow (developers)
1. Load new metrics and mutations.
2. Recompute rankings and mutation introductions.
3. Regenerate embeddings if needed.
4. Refresh materialized views.

```sql
select refresh_bonus_materialized_views();
```

## Quick checks
```sql
select count(*) from variant_performance_rankings;
select count(*) from mutation_introduction_events;
select count(*) from mv_activity_landscape;
select count(*) from mv_domain_mutation_enrichment;
```

## Troubleshooting
- Empty landscape: no embeddings loaded in `embedding_points`
- Missing top variants: rerun ranking step by generation
- Stale views: run `refresh_bonus_materialized_views()`

## Glossary
- Variant: engineered sequence derived from a wild-type protein
- Generation: evolution round within an experiment
- Activity score: derived metric used for ranking
- Embedding: 2D coordinates used for the landscape plot

## Reference
- Mead DJT, Lunagomez S, Gatherer D. Visualization of protein sequence space
	with force-directed graphs, and their application to the choice of
	target-template pairs for homology modelling. J Mol Graph Model. 2019;92:180-191.
	https://doi.org/10.1016/j.jmgm.2019.07.014
- Selles Vidal L, Isalan M, Heap JT, Ledesma-Amaro R. A primer to directed evolution:
	current methodologies and future directions. RSC Chem Biol. 2023;4:271-291.
	https://doi.org/10.1039/D2CB00231K
- Geard N, Wiles J. Directed Evolution of an Artificial Cell Lineage. In: Randall M,
	Abbass HA, Wiles J (eds) Progress in Artificial Life. ACAL 2007. LNCS 4828.
	Springer, Berlin, Heidelberg. https://doi.org/10.1007/978-3-540-76931-6_13
- Mule MP, Martins AJ, Tsang JS. Normalizing and denoising protein expression data
	from droplet-based single cell profiling. Nat Commun. 2022;13:2099.
	https://doi.org/10.1038/s41467-022-29356-8
- O'Rourke MB, Town SEL, Dalla PV, Bicknell F, Koh Belic N, Violi JP, Steele JR,
	Padula MP. What is Normalization? The Strategies Employed in Top-Down and
	Bottom-Up Proteome Analysis Workflows. Proteomes. 2019;7(3):29.
	https://doi.org/10.3390/proteomes7030029
- Mirzaei G. Constructing gene similarity networks using co-occurrence
	probabilities. BMC Genomics. 2023;24:697.
	https://doi.org/10.1186/s12864-023-09780-w
