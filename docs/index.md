# Tahoe Project 2026

Directed evolution sequence processing pipeline for variant analysis.

## Overview

This pipeline processes DNA variants from directed evolution experiments:

1. **WT Mapping** — Locates the wild-type gene in a circular plasmid via 6-frame protein alignment
2. **Variant Processing** — Extracts CDS from each variant plasmid, translates to protein, runs QC
3. **Mutation Calling** — Detects synonymous, nonsynonymous, indel, and frameshift mutations
4. **Persistence** — Stores results, mutations, and metrics in PostgreSQL

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set database connection
export DATABASE_URL='postgresql+psycopg://user:pass@host:5432/dbname'

# Run pipeline for an experiment
python -m app.jobs.run_sequence_processing <experiment_id>
```

## Project Structure

```
app/
├── config.py                      # Environment-based settings
├── jobs/
│   └── run_sequence_processing.py # Pipeline orchestrator + CLI
├── services/sequence/
│   ├── db_repo.py                 # Database persistence layer
│   ├── sequence_service.py        # Core processing logic
│   └── uniprot_service.py         # UniProt API client
└── utils/
    └── seq_utils.py               # DNA/protein utility functions
tests/
├── test_submit_sequence_processing.py  # Unit tests (mocked DB)
├── test_submit_live_db.py              # Live DB integration test
├── test_uniprot_service.py             # UniProt service tests
└── test_variant_analysis.py            # Variant analysis integration test
```
