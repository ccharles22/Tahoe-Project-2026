# Testing

## Running Tests

```bash
# Unit tests (no database required)
python -m pytest tests/test_submit_sequence_processing.py -v

# UniProt service tests (mocked network)
python -m pytest tests/test_uniprot_service.py -v

# Live database integration test (requires DATABASE_URL)
python -m pytest tests/test_submit_live_db.py -v -s

# Variant analysis integration test
python tests/test_variant_analysis.py --experiment 2 --max 5
```

## Test Structure

| File | Type | DB Required | Description |
|------|------|-------------|-------------|
| `test_submit_sequence_processing.py` | Unit | No | Pipeline orchestration, QC status, frame handling, indels |
| `test_uniprot_service.py` | Unit | No | UniProt API client with mocked HTTP |
| `test_submit_live_db.py` | Integration | Yes | End-to-end pipeline against live PostgreSQL |
| `test_variant_analysis.py` | Integration | Yes | Variant processing and mutation calling |

## Key Test Scenarios

### QC-Based Status Reporting
Tests verify that `ANALYSED_WITH_ERRORS` is set when variants have:

- Frameshifts (`has_frameshift=True`)
- Failed translation (`protein_aa=None`)
- Premature stop codons (`has_premature_stop=True`)
- Processing exceptions

### Non-Zero Reading Frames
Tests with `frame=1` and `frame=2` confirm that CDS extraction uses coordinates
directly without double-trimming the frame offset.

### Indel Detection
Tests verify that insertion and deletion mutations are detected when WT and variant
CDS have different lengths, routing through protein alignment.
