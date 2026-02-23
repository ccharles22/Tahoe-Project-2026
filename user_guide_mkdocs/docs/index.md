# Project documentation

This site documents the PostgreSQL schema, data pipelines, and visualization outputs for the project.

## What to start with
- Database: high-level schema overview and key tables.
- Plots: where each visualization pulls its data from.
- Pipelines: how rankings, mutation events, and embeddings are generated.

## Quick start
1. Install docs dependencies with `pip install mkdocs mkdocs-material`.
2. Run `mkdocs serve` from the `user_guide_mkdocs` folder.
3. Open http://localhost:8000.

## What is in scope
- PostgreSQL schema and bonus visualization tables
- Data processing pipelines (rankings, mutation events, embeddings)
- Plot inputs and refresh steps

## How to contribute
- Keep changes small and focused per page
- Prefer short sections with clear headings
- Update both the database and the docs when schemas change
