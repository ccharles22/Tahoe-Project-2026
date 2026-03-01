# Plots and data sources

This section explains how each core visualisation should be read, not just where
it gets its data. Together, the plots are meant to answer different questions
about the same experiment:

- **Top 10**: which variants rank highest by unified activity score
- **Distribution**: how activity changes across generations
- **Lineage**: how variants are related through parent-child inheritance
- **Protein network**: which variants are similar by sequence or shared
  mutations

## How the plots complement each other

The four main plots are designed to be interpreted together:

- Top 10 shows the best-performing rows
- Distribution shows whether those top performers sit inside a broad shift or a
  narrow outlier band
- Lineage shows whether high performers emerge from one successful branch or
  many independent branches
- Protein similarity shows whether similar performers share common mutation
  patterns even when they are not directly related by ancestry

## How plots are generated in this repo

- Batch mode: `python -m scripts.run_report` writes files to
  `app/static/generated`
- Endpoint mode: Flask routes generate plot files into `app/static/plots` when
  requested

## Flask routes

- `/top10/<experiment_id>`
- `/distribution/<experiment_id>`
- `/lineage/<experiment_id>`
- `/protein_similarity/<experiment_id>`

## Quick verification checklist

1. the endpoint responds without template or database errors
2. a new image file appears in `app/static/plots`
3. the plot contains real data rather than an empty or placeholder view
4. the plot matches the requested experiment ID
