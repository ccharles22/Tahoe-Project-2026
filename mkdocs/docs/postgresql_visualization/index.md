# Project documentation

This site documents how the repository is used end-to-end:
- PostgreSQL schema and constraints
- Metrics computation and plotting scripts
- Flask endpoints for generated visualizations
- Bonus pipelines and materialized views

## Start here
1. Read **Database** for table relationships and refresh rules.
2. Read **Pipelines** for compute order and validation checks.
3. Read **Plots** for data sources and parameter tuning.
4. Read **User guide** for day-to-day usage.

## Quick start (docs)
From the repository root:

```bash
cd mkdocs
mkdocs serve -a 127.0.0.1:8000
```

Open: `http://127.0.0.1:8000`

## Quick start (project runtime)
From the repository root:

```bash
export DATABASE_URL="postgresql://<user>:<password>@<host>:5432/bio727p_group_project"
export EXPERIMENT_ID=41
python -m scripts.run_report
python -m src.analysis_MPL.app
```

Then open:
- `/top10/41`
- `/distribution/41`
- `/lineage/41`
- `/protein_similarity/41`

## Outputs generated
Files are written to `app/static/generated` (report) and `app/static/plots` (Flask endpoint rendering), including:
- top-10 table PNG/CSV
- activity distribution PNG
- lineage PNG
- protein network PNG

## Contribution rules for docs
- Keep commands executable as written.
- Prefer explicit paths and SQL snippets over prose.
- Update docs in the same PR as schema or pipeline changes.
