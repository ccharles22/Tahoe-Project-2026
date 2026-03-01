# Running the Pipeline

The bonus visualisation pipeline is a single CLI command that:

1. Ensures metric definitions exist in the database.
2. Precomputes PCA (and optionally t-SNE) embeddings.
3. Creates/refreshes materialized views.
4. Generates all four HTML visualisations.

## Prerequisites

- PostgreSQL database with the Tahoe Project schema populated.
- `activity_score` metrics already computed for the target generation.
- Python virtual environment with dependencies installed:

```bash
pip install -r requirements.txt
```

## Basic usage

```bash
python -m analysis.pipelines.run_bonus_pipeline \
    --generation-id 1 \
    --skip-create-views \
    --skip-refresh-views
```

This writes four HTML files to `outputs/`:

| File | Content |
|---|---|
| `activity_landscape_pca_surface_all_gens.html` | 3-D activity landscape |
| `mutation_fingerprint_selector.html` | Fingerprint with dropdown selector |
| `domain_enrichment_heatmap.html` | Domain enrichment heatmap |
| `mutation_frequency_by_position.html` | Positional mutation frequency |

## Shell wrapper

A convenience script is provided for Linux/macOS:

```bash
bash scripts/run_all_bonus.sh [GEN] [MODE] [METHOD] [GRID] [INCLUDE_TSNE]
# defaults: GEN=1  MODE=surface  METHOD=pca  GRID=60  INCLUDE_TSNE=0
```

## Materialized views

The pipeline depends on two materialized views:

- `mv_activity_landscape` — PCA/t-SNE coordinates + activity scores.
- `mv_domain_mutation_enrichment` — per-domain mutation counts.

If these already exist in the database, pass `--skip-create-views` to avoid
needing DDL privileges.  Pass `--skip-refresh-views` if your DB role cannot
run `REFRESH MATERIALIZED VIEW`.

## Variant selection

By default, the fingerprint selector picks the **10 highest-activity variants
with the deepest lineage** (at least 5 ancestor generations), so the plot
shows mutations accumulated across multiple rounds of evolution.  Override
with `--fingerprint-variant-id <id>` to plot a specific variant.
