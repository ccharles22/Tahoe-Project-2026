# Plots and data sources

This section maps each visualization to its data source. Use the pages below for details and examples:

- Lineage: lineage and mutation fingerprinting data sources
- Distribution: activity score distribution inputs
- Top 10: ranking table inputs
- Protein network: identity and co-occurrence inputs

## Shared notes
- The materialized views are refreshed by `refresh_bonus_materialized_views()`.

## How plots are generated in this repo
- Batch mode: `python -m scripts.run_report` writes files to `app/static/generated`.
- Endpoint mode: Flask routes generate plot files into `app/static/plots` when requested.

## Flask routes
- `/top10/<experiment_id>`
- `/distribution/<experiment_id>`
- `/lineage/<experiment_id>`
- `/protein_similarity/<experiment_id>`

## Quick verification checklist
1. Endpoint responds without template/database errors.
2. New image file appears in `app/static/plots`.
3. Plot has non-empty data (not placeholder text).
4. Plot matches expected experiment ID.
