# Bonus Visualisations

This module produces four interactive Plotly visualisations that summarise the
directed-evolution experiment run by the Tahoe Project pipeline.

## Outputs

| Visualisation | Output file | Description |
|---|---|---|
| Activity Landscape | `activity_landscape_pca_surface_all_gens.html` | 3-D surface (or scatter) of PCA-embedded mutation vectors coloured by activity score |
| Mutation Fingerprinting | `mutation_fingerprint_selector.html` | Per-variant lollipop chart with a dropdown selector; shows every amino-acid change coloured by the generation it was introduced |
| Domain Enrichment | `domain_enrichment_heatmap.html` | Heatmap of non-synonymous mutation counts per protein domain across all generations |
| Mutation Frequency | `mutation_frequency_by_position.html` | Two-panel chart — total mutation counts per amino-acid position (top) and per-generation stacked area (bottom) |

## Quick start

```bash
# activate your virtual environment
source venv/bin/activate        # Linux / macOS
venv\Scripts\activate           # Windows

# run the full pipeline (generation 1, surface mode)
python -m analysis.pipelines.run_bonus_pipeline \
    --generation-id 1 \
    --skip-create-views \
    --skip-refresh-views
```

All outputs are written to `outputs/` by default.

## Project layout

```
visualisations/          # Plotly plotting modules (one per chart)
analysis/
  pipelines/
    run_bonus_pipeline.py  # Orchestrator — CLI entry-point
  database/
    postgres.py            # DB connection helper
  embeddings/
    precompute_embeddings.py
sql/
  views/                   # Materialized-view DDL used by the pipeline
scripts/
  run_all_bonus.sh         # Convenience wrapper
docs/                      # This documentation (MkDocs source)
```
