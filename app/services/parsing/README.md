# Data Parsing & QC Module

## Overview
This module handles uploading, parsing, and quality control of experimental directed evolution data.

## Supported Formats
- **TSV**: Tab-delimited text files
- **CSV**: Comma-delimited text files  
- **JSON**: JSON array or nested object structures

## Usage

### Parse a file
```python
from parsing.tsv_parser import TSVParser
from parsing.qc import QualityControl
- Error/warning rules
# Data Parsing & QC Module

## Overview
This package provides parsers and validation for directed-evolution experimental data. It
keeps parsing, normalization, and quality-control logic separate so you can reuse the
parsers (`TSVParser`, `JSONParser`) and the `QualityControl` validator independently.

### Main components
- `parsing/base_parser.py` — shared parser base class (normalization, metadata, summary, validate_all)
- `parsing/tsv_parser.py` — TSV/CSV parser with delimiter detection and row cleaning
- `parsing/json_parser.py` — JSON parser that extracts records from several common layouts
- `parsing/qc.py` — QualityControl: per-record and cross-record validation, plus optional
    percentile-mode for data-driven thresholds
- `parsing/config.py` — central FIELD_MAPPING, REQUIRED/OPTIONAL fields and validation defaults

## Supported formats
- TSV (tab-delimited) and CSV (comma-delimited). `TSVParser` auto-detects delimiter from the first line.
- JSON arrays, or nested JSON objects containing `records` or `variants`, or a single object.

## Quick usage

Parse a TSV and run validation (per-record + cross-record):

```python
from parsing.tsv_parser import TSVParser
from parsing.qc import QualityControl

parser = TSVParser('data/parsing/DE_BSU_Pol_Batch_1.tsv')
success = parser.parse()
if not success:
        print('Parse errors:', parser.errors)

# Default QC
qc = QualityControl()
parser.validate_all(qc)
print(parser.get_summary())
```

Enable percentile-based, data-driven thresholds (recommended for exploratory runs):

```python
qc = QualityControl(percentile_mode=True, percentile_low=5.0, percentile_high=95.0)
parser.validate_all(qc)
```

You can also pass a small `config` dict to `QualityControl(config=...)` to override `VALIDATION_RULES`.

## Field mapping and normalization
Field names in incoming files are normalized using `FIELD_MAPPING` in `parsing/config.py`.
Mappings are case-sensitive in the current implementation; add alternates to the list for
robustness (e.g. `"variant_id"`, `"id"`, `"Plasmid_Variant_Index"` → `variant_index`).

The parsers also normalize DNA sequence strings (uppercasing, removing spaces) and attempt
to coerce numeric-ish columns to `int`/`float` for common fields.

## Validation details

Per-record checks (implemented in `QualityControl.validate_record`):
- Required fields presence and non-empty values
- Simple type checks (ints for variant indices/generation, numeric yields)
- Sequence checks (min/max length, allowed characters, frameshift warning)

Cross-record checks (implemented in `QualityControl.validate_cross_record`):
- Duplicate `variant_index` detection
- Missing generation 0 warning
- Missing generations (continuity)
- Orphaned parent variants (parent index not found in dataset)

Thresholds and behaviour
- Defaults live in `parsing/config.py` (VALIDATION_RULES, ERROR_THRESHOLDS, WARNING_THRESHOLDS).
- Per-metric overrides are supported (e.g. `protein_yield_min_warning`).
- Percentile-mode computes dataset percentiles and sets per-metric min/max warnings automatically.

## Example: percentile-mode in the summary tool
The repository includes `scripts/parsing/qc_summary.py` which runs parsing + QC and prints computed
percentile thresholds (5th/95th by default) then runs validation using those thresholds.

Run it from the repo root with your venv active:

```bash
# with venv activated
PYTHONPATH=. python scripts/parsing/qc_summary.py
```

## Database schema (suggested)
The project does not include DB wiring, but the following schema is a recommended target for
storing parsed variants:

```sql
CREATE TABLE variants (
        id INTEGER PRIMARY KEY,
        experiment_id INTEGER NOT NULL,
        variant_index INTEGER NOT NULL,
        generation INTEGER NOT NULL,
        parent_variant_index INTEGER,
        assembled_dna_sequence TEXT NOT NULL,
        dna_yield REAL,
        protein_yield REAL,
        additional_metadata JSON,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Testing
- Run the full test suite: `pytest -q`
- Run a single test: `pytest tests/test_qc.py::test_missing_required_fields -q`

## Notes and next steps
- Consider making `FIELD_MAPPING` case-insensitive (lowercasing incoming headers) for robustness.
- For reproducible production pipelines, persist chosen numeric thresholds (from percentile-mode)
    into a config file and use those stable values for reporting/alerts.

If you'd like, I can:
- Add a `--persist` option to `scripts/parsing/qc_summary.py` to write computed thresholds to a JSON file.
- Add a unit test that asserts `QualityControl(percentile_mode=True)` computes expected percentiles.

## File Upload API

### Endpoints

#### POST /parsing/upload
Upload and parse experimental data files.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Parameters:
    - `file`: TSV, CSV, or JSON file (required)
    - `experiment_id`: Integer experiment ID (optional, default=1)
    - `persist_thresholds`: Boolean for percentile mode (optional, default=false)

**Response:**
- Success (200):
```json
    {
        "success": true,
        "total_records": 100,
        "inserted_count": 100,
        "warnings": [],
        "warnings_count": 0,
        "detected_fields": ["variant_index", "generation", "assembled_dna_sequence"]
    }
```
- Client Error (400): Invalid file or validation errors
- Server Error (500): Database error

**Security:**
- File size limited to 50 MB
- Only `.tsv`, `.csv`, `.json` extensions allowed
- Filenames sanitized with `secure_filename()`
- Temporary files cleaned up after processing

#### GET /parsing/health
Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### Setup Database
```python
from app import create_app
from app.extensions import db

app = create_app()
with app.app_context():
    db.create_all()
```

### Example Usage
```bash
# Upload TSV file
curl -X POST http://localhost:5000/parsing/upload \
    -F "file=@data/parsing/DE_BSU_Pol_Batch_1.tsv" \
    -F "experiment_id=1"

# Upload JSON file
curl -X POST http://localhost:5000/parsing/upload \
    -F "file=@data/parsing/DE_BSU_Pol_Batch_1.json" \
    -F "experiment_id=2"
```
