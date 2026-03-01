# BIO727P Documentation

Welcome to the unified project documentation.

## Homepage navigation

The homepage acts as the main entry point to the platform. Use it to move
between the major parts of the application quickly:

- **Home** keeps you on the public landing page.
- **Workspace** opens the experiment workspace, where sequence processing,
  analysis, and report generation are managed.
- **User Guide** opens the documentation hub so users can jump directly to
  parsing, metrics, visualisation, and bonus-guide sections.
- The **results preview carousel** on the homepage gives a quick view of the
  kinds of plots and outputs the platform can generate before entering the
  workspace.

The homepage navigation bar is intended to provide lightweight orientation,
while the experiment workspace handles the step-by-step pipeline workflow.

## Documentation Areas

- **Parsing & QC**: Data ingestion, validation rules, quality-control checks, and API usage.
  - Start here: [Parsing & QC Overview](parsing_qc/index.md)
- **PostgreSQL & Visualization**: Database design, pipelines, and generated plots.
  - Start here: [PostgreSQL & Visualization Overview](postgresql_visualization/index.md)
- **Bonus Visualisations**: Advanced optional analysis outputs such as activity
  landscapes, mutation fingerprinting, domain enrichment, and mutation
  frequency summaries.
  - Start here: [Bonus Visualisations Overview](bonus_visualisations/index.md)

## Ownership Model

Each area keeps its own `OWNERS.md` file and scoped assets/content paths:

- `docs/parsing_qc/*`
- `docs/postgresql_visualization/*`

This keeps contribution boundaries explicit while publishing through one MkDocs site.
