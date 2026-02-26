# BIO727P Documentation

Welcome to the unified project documentation.

## Documentation Areas

- **Parsing & QC**: Data ingestion, validation rules, quality-control checks, and API usage.
  - Start here: [Parsing & QC Overview](parsing_qc/index.md)
- **PostgreSQL & Visualization**: Database design, pipelines, and generated plots.
  - Start here: [PostgreSQL & Visualization Overview](postgresql_visualization/index.md)

## Ownership Model

Each area keeps its own `OWNERS.md` file and scoped assets/content paths:

- `docs/parsing_qc/*`
- `docs/postgresql_visualization/*`

This keeps contribution boundaries explicit while publishing through one MkDocs site.