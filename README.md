# Tahoe-Project

Flask application for directed-evolution experiment staging, parsing, sequence processing, and analysis.

## Project Structure

- `app/`: application code (Flask app, blueprints, services, templates, static assets)
- `tests/`: pytest suites
- `scripts/`: operational and debugging scripts
- `docs/`: MkDocs documentation
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
