# Architecture

This project uses a Flask application-factory pattern with blueprint-based routing and service-layer business logic.

## Folder Ownership Rules

- `app/blueprints/*`: HTTP routes and request/response orchestration only.
- `app/services/*`: domain logic, external integrations, and data processing.
- `app/models.py`: SQLAlchemy models.
- `app/templates/` and `app/static/`: UI assets.
- `scripts/`: one-off or operational entry scripts; not imported by app runtime.
- `tests/`: automated verification.

## Key Decisions

- Single app factory at `app/__init__.py`.
- Single routing pattern via blueprints in `app/blueprints/`.
- Single UniProt integration module at `app/services/uniprot_service.py`.
- Analysis code source of truth in `app/services/analysis/`.

## Conventions

- New routes must be added through a blueprint package under `app/blueprints/`.
- New business logic should be added under the appropriate `app/services/<domain>/`.
- Avoid introducing parallel package roots (for example, a second `src/` runtime tree).
