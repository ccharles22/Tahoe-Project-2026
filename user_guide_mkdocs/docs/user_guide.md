# User guide

This guide is the operational runbook for running the project, verifying results, and recovering from common failures.

## Who this is for
- Viewers: open the plots and understand what they show
- Analysts: pull data for ad hoc checks
- Developers: refresh pipelines and materialized views

## Prerequisites
- Python environment with dependencies installed (`requirements.txt`)
- PostgreSQL reachable through `DATABASE_URL`
- Schema applied from `schema/schema.sql`

## Environment variables
Set these before running scripts:

```bash
export DATABASE_URL="postgresql://<user>:<password>@<host>:5432/bio727p_group_project"
export EXPERIMENT_ID=41
```

Optional:
- `PROTEIN_NET_MODE=identity` or `PROTEIN_NET_MODE=cooccurrence` for `scripts.run_report`

## Daily operations checklist
1. Confirm DB connectivity:
   `python -m scripts.test_connection`
2. Generate metrics + core plots:
   `python -m scripts.run_report`
3. If mutation embeddings changed:
   `python -m scripts.generate_pca_embeddings`
4. Refresh bonus materialized views:
   `select refresh_bonus_materialized_views();`
5. Open Flask endpoints and verify images render:
   - `/top10/<experiment_id>`
   - `/distribution/<experiment_id>`
   - `/lineage/<experiment_id>`
   - `/protein_similarity/<experiment_id>`

## Runtime commands
### Generate report artifacts
```bash
python -m scripts.run_report
```
Expected outputs in `app/static/generated`:
- `exp_<id>_stage4_qc_debug.csv`
- `exp_<id>_top10_variants.csv`
- `exp_<id>_activity_distribution.png`
- `exp_<id>_lineage.png`
- `exp_<id>_protein_similarity*.png`

### Start Flask app
```bash
python -m src.analysis_MPL.app
```

### Serve documentation
```bash
cd user_guide_mkdocs
mkdocs serve -a 127.0.0.1:8000
```

## Plot usage (viewers)
- Lineage: parent-child structure across generations
- Distribution: activity score spread by generation
- Top10: highest activity variants in experiment
- Protein network: identity or co-occurrence relationships

### Protein network quick start
- Identity:
  `/protein_similarity/41?mode=identity&identity_threshold=0.95`
- Co-occurrence:
  `/protein_similarity/41?mode=cooccurrence&min_shared=2&jaccard_threshold=0.1`

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
- Raw and derived scoring: `metrics`, `variants`, `generations`
- Mutation context: `mutations`
- Optional bonus views: `mv_activity_landscape`, `mv_domain_mutation_enrichment`

## Refresh workflow (developers)
1. Load new metrics and mutations.
2. Recompute derived metrics and plots.
3. Regenerate embeddings if needed.
4. Refresh materialized views.

```sql
select refresh_bonus_materialized_views();
```

## Quick checks (SQL)
```sql
-- Derived metric presence
select count(*) as n_activity_scores
from metrics
where metric_name='activity_score'
  and metric_type='derived';

-- Derived metric coverage for one experiment
select count(*) as n_exp_scores
from metrics m
join variants v on v.variant_id = m.variant_id
join generations g on g.generation_id = v.generation_id
where m.metric_name='activity_score'
  and m.metric_type='derived'
  and g.experiment_id = 41;

-- Optional bonus view row counts
select count(*) from mv_activity_landscape;
select count(*) from mv_domain_mutation_enrichment;
```

## Troubleshooting and recovery
### 1) `DATABASE_URL not set` or connection failure
Symptoms:
- script exits before querying data
- psycopg2 connection errors

Recovery:
1. export a valid `DATABASE_URL`
2. run `python -m scripts.test_connection`
3. rerun report

### 2) Empty Top 10 or distribution output
Symptoms:
- blank/empty CSV for top10
- distribution plot not generated

Likely cause:
- missing derived `activity_score`

Recovery:
1. run `python -m scripts.run_report`
2. check QC CSV in `app/static/generated`
3. run SQL quick checks for derived metrics

### 3) Lineage plot has nodes but no edges
Symptoms:
- scattered points with no connecting lines

Likely causes:
- `parent_variant_id` missing in loaded variants
- upstream data did not preserve parent links

Recovery:
1. verify parent IDs in DB
2. reload variants with parent mapping
3. rerun report

### 4) Co-occurrence protein network is empty
Symptoms:
- message indicating no shared protein mutations

Likely causes:
- no `mutation_type='protein'` rows
- thresholds too strict

Recovery:
1. verify mutation rows exist
2. try `preset=medium` or `preset=dense`
3. lower `min_shared` and remove Jaccard threshold

### 5) Landscape or domain views are stale
Symptoms:
- old values despite new pipeline runs

Recovery:
1. run `select refresh_bonus_materialized_views();`
2. rerun row-count checks
3. reload UI or query again

## Incident checklist (fast triage)
1. Confirm DB connectivity.
2. Confirm derived metric presence.
3. Confirm experiment-specific row counts.
4. Regenerate report outputs.
5. Refresh materialized views.
6. Re-open endpoints and inspect generated files.

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
