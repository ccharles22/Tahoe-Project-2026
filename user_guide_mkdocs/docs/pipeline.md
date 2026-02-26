# Pipelines

This page describes the compute order used by this repository.

## Activity score details
For the full formulas and QC states, see:
- [Activity score calculations](activity_score_calculations.md)

## Stage 1: Load raw data
Use your loader to insert:
- generations
- variants
- raw metrics (`dna_yield_raw`, `protein_yield_raw`)
- WT controls (when available)

In this repo, example loader:

```bash
export DATASET_PATH=/path/to/data.tsv
export EXPERIMENT_ID=41
python -m scripts.load_example_data
```

## Stage 2: Compute activity metrics + generate plots
Run:

```bash
export EXPERIMENT_ID=41
python -m scripts.run_report
```

Optional controls:

```bash
# Scoring behavior: auto | wt | fallback
export SCORING_MODE=auto

# Protein network behavior: cooccurrence | identity
export PROTEIN_NET_MODE=cooccurrence
```

What this does:
- fetches variant raw metrics
- computes activity with selected scoring mode:
  - WT-based when valid WT baselines are available
  - fallback median normalization when configured/required
- upserts `dna_yield_norm`, `protein_yield_norm`, `activity_score`
- writes CSV + PNG outputs in `app/static/generated`

## Rankings and mutation introductions
- Compute top-10 variants per generation by activity score.
- Trace lineage to record the first appearance of each mutation.

### Recommended cadence
- Recompute after new metrics are loaded
- Recompute if lineage is backfilled

## Embeddings (PCA)
- Build feature vectors from protein mutation positions per variant.
- Run PCA for 2D coordinates.
- Store results in `embedding_runs` and `embedding_points`.

Example:

```bash
python -m scripts.generate_pca_embeddings
```

### Inputs
- Variants with `activity_score`
- Protein mutation positions

## Refresh
After any pipeline run, refresh materialized views:

```sql
select refresh_bonus_materialized_views();
```

## Validation checks
- `embedding_points` row count should match variants with `activity_score`
- `mv_activity_landscape` row count should match `embedding_points`

## Recommended execution order
1. Load raw data.
2. Run report (`scripts.run_report`) for derived metrics and base plots.
3. Run embeddings (`scripts.generate_pca_embeddings`) when mutation data exists.
4. Refresh materialized views.
5. Re-open plot endpoints and verify output files.

## Common failures
- No distribution/top10 data: check `metrics` contains derived `activity_score`.
- Empty co-occurrence network: check protein mutations exist in `mutations`.
- Empty lineage edges: parent links may be missing in loaded variants.
- WT strict-mode failure: set `SCORING_MODE=auto` or `SCORING_MODE=fallback` for synthetic/no-WT experiments.

## Known issue: sequence-processing pipeline
- Root cause appears in sequence-processing code, not SQL schema design.
- Evidence: variants with protein length 1-8 show approximately 874 mutations, which is biologically implausible for this dataset.
- Suspected bug points:
  - Double frame trim during ORF/translation handling.
  - Fragile alignment parsing based on `aln.format()` output.
  - WT boundary over-extension during mutation coordinate mapping.
- Affected experiments:
  - `1`, `41`, `74`, `76`, `77`, `78`

### Immediate handling guidance
- Treat mutation-level outputs from affected experiments as unreliable until sequence processing is fixed.
- Prioritize review of frame trimming, alignment parsing, and WT boundary checks before re-running mutation extraction.
