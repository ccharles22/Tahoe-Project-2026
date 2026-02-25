# Tahoe-Project

Flask application for directed-evolution experiment staging, parsing, sequence processing, and analysis.

## Project Structure

- `app/`: application code (Flask app, blueprints, services, templates, static assets)
- `tests/`: pytest suites
- `scripts/`: operational and debugging scripts
- `mkdocs/parsing_qc/`: MkDocs docs/site/config for parsing & QC
- `mkdocs/postgresql_visualization/`: MkDocs docs/site/config for PostgreSQL visualization docs
- `schema/`: SQL schema and published data artifacts
- `data/`: local sample/input data files

## App Entry

- Runtime factory: `app/__init__.py`
- Development entrypoint: `run.py`

## Routing

- `app/blueprints/auth/`
- `app/blueprints/staging/`
- `app/blueprints/parsing/`
- `app/blueprints/sequence/` (API routes under `/api`)

## Services

- `app/services/parsing/`
- `app/services/staging/`
- `app/services/sequence/`
- `app/services/analysis/`
- Canonical UniProt client: `app/services/uniprot_service.py`

## Scripts

- `scripts/run_report.py`: run analysis/report generation
- `scripts/exported_lineage.py`: lineage export helper
- `scripts/debug/`: ad-hoc investigation scripts

## Local Run

```bash
python run.py
```

## PostgreSQL + Visualization Pipeline

This repo also includes an end-to-end PostgreSQL analysis/visualization flow for experiment metrics and reporting.

### Features
- Relational schema for users, experiments, generations, variants, mutations, and metrics
- Derived metrics (DNA/protein normalization plus activity score)
- Lineage closure/views for network plots
- Static plot generation and simple Flask endpoints for viewing results

### Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Create a `.env` entry for `DATABASE_URL`
3. Apply schema: `psql "$DATABASE_URL" -f schema/schema.sql`

### Reports
- Generate: `python -m scripts.run_report`
- Outputs are written under `app/static/generated/`
