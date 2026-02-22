# PostgreSQL Repository and Data Visualization (MPL)

End-to-end pipeline for storing directed evolution experiment data in PostgreSQL
and generating summary visualizations (top variants, activity distributions,
lineage networks, and protein similarity networks).

## Features
- Relational schema for users, experiments, generations, variants, mutations, and metrics
- Derived metrics (DNA/protein normalization + activity score)
- Lineage closure and lineage views for network plots
- Static plot generation and simple Flask endpoints for viewing results

## Project Structure
- schema/schema.sql: database schema and triggers
- src/analysis_MPL: core logic (queries, metrics, plots)
- scripts/run_report.py: generate plots and CSV outputs
- app: HTML templates and generated static outputs

## Requirements
- Python 3.10+
- PostgreSQL (tested with 18.x)
- A database named bio727p_group_project

Install dependencies:
```bash
pip install -r requirements.txt
```

## Setup
1. Create a .env file with:
```
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/bio727p_group_project
```

2. Apply schema:
```bash
psql "$DATABASE_URL" -f schema/schema.sql
```

## Generate Reports
The report script writes outputs to app/static/generated.

```bash
export EXPERIMENT_ID=41
python -m scripts.run_report
```

## Generated Graphs
For each experiment, the report produces four plots in app/static/generated:
- Top-10 variants table: exp_<experiment_id>_top10_variants.png
- Activity distribution by generation: exp_<experiment_id>_activity_distribution.png
- Lineage network: exp_<experiment_id>_lineage.png
- Protein similarity network: exp_<experiment_id>_protein_similarity.png

## Flask App (optional)
```bash
python -m src.analysis_MPL.app
```
Then open:
- /top10/<experiment_id>
- /distribution/<experiment_id>
- /lineage/<experiment_id>

## Notes
- The schema includes triggers for activity metrics and lineage maintenance.
- If you already hash passwords in the app, disable the password hashing trigger.
