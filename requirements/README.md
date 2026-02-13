# Tahoe Project 2026 - Sequence Processing Pipeline

## Overview
This repository comprises of a Python-based bioinformatics pipeline created for the MSc Bioinformatics Group Project. The software processes plasmid DBA variant sequences, establishes the recombinant gene of interest, executes in-silico translation and transcription, and categorises mutations relative to a wild-type (WT) reference protein obtained from UniProt.

The system is organised to be reproducible, modular, and database-backed, supporting downstream analysis and reporting.

---

## Key Features
- Retrieval of WT protein sequences from UniProt using accession IDs
- Identification of coding regions within plasmid DNA
- In-silico DNA -> protein translation with quality-control flags
- Mutation detection and classification (synonmyous vs non-synonymous)
- Persistent storage of analysis outputs in MariaDB
- Deterministic, re-runnable analysis pipeline

---

## Project Structure
app/
utils/ # Low-level sequence utilities (translation, slicing, QC)
services/ # Biological logic and database access
jobs/ # Analysis job entry points
requirements.txt
README.md

---

## Requirements
- Python 3.10+
- MariaDB (local or remote instance)

Python dependencies are listed in 'requirements.txt'

---

## Setup Instructions
### 1. Clone the repository
```bash
git clone <repository-url>
cd Tahoe-Project-2026

### 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/active

### 3. Install dependencies
pip instal -r requiremnts.txt

### 4. Configure environment variables
create an .env file or set environment variables with:
- DATABASE_URL - MariaDb connection string

---

## Running the Analysis
### Staging (WT protein retrieval)
Obtain and store the WT protein sequence from UniProt
This step is carried out once per experiment and persists the WT reference for reproducible analysis

## Sequence Processing Job
Run the analysis pipeline for a given experiment ID:
python -m app.jobs.run_sequence_processing <experiment_id>

the job:
1. Loads staged WT references from the database
2. Maps the recombinant gene within the plasmid
3. Processes each variant determinsttically
4. Stores protein sequences, Qc flags and mutation data

---

### Output
All analysis outputs are stored in MariaDB including:
- Translated protein sequences
- Mutation classifications and counts
- Quality-control flags
- Experiment processing status
These stored results are intended for downstream visualisation and reporting.

---

### Notes
- The analysis pipeline is deterministic: identical inputs always produce identical outputs.
- External services (UniProt) are accessed only during staging, not during analysis runs.
- The codebase follows a layered design to separate utilities, biological logic, persistence and orchestration.

---

### Authors
Team Tahoe - Patricia 