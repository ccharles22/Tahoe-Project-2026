"""
Unit tests for parsers.
"""

import pytest
from app.services.parsing.tsv_parser import TSVParser
from app.services.parsing.json_parser import JSONParser
from app.services.parsing.qc import QualityControl


def test_tsv_delimiter_detection():
    """Test that TSV parser correctly detects tab delimiter."""
    parser = TSVParser("data/parsing/DE_BSU_Pol_Batch_1.tsv")

    with open("data/parsing/DE_BSU_Pol_Batch_1.tsv", "r") as f:
        first_line = f.readline()

    delimiter = parser._detect_delimiter(first_line)
    assert delimiter == "\t"


def test_tsv_parsing():
    """Test basic TSV parsing."""
    parser = TSVParser("data/parsing/DE_BSU_Pol_Batch_1.tsv")
    success = parser.parse()

    assert success is True
    assert len(parser.records) > 0
    assert len(parser.errors) == 0


def test_json_parsing():
    """Test basic JSON parsing."""
    parser = JSONParser("data/parsing/DE_BSU_Pol_Batch_1.json")
    success = parser.parse()

    assert success is True
    assert len(parser.records) > 0
    assert len(parser.errors) == 0


def test_full_tsv_workflow():
    """Test complete parsing + QC workflow with BSU TSV file."""

    # --- Step 1: Parse TSV ---
    parser = TSVParser("data/parsing/DE_BSU_Pol_Batch_1.tsv")
    success = parser.parse()
    assert success is True, "TSV parsing failed"

    # --- Step 2: Run QC (per-record + cross-record) ---
    # Use percentile-mode so thresholds are computed from this dataset
    qc = QualityControl(percentile_mode=True, percentile_low=5.0, percentile_high=95.0)

    # Compute and show thresholds derived from the dataset, then run validation
    qc.compute_thresholds_from_records(parser.records)
    print("\nComputed thresholds:")
    print(f"  dna_yield_min_warning: {qc.dna_yield_min_warning}")
    print(f"  dna_yield_max_warning: {qc.dna_yield_max_warning}")
    print(f"  protein_yield_min_warning: {qc.protein_yield_min_warning}")
    print(f"  protein_yield_max_warning: {qc.protein_yield_max_warning}\n")

    parser.validate_all(qc)

    # --- Step 3: Get summary ---
    summary = parser.get_summary()

    print("\n=== PARSING SUMMARY ===")
    print(f"Total records: {summary['total_records']}")
    print(f"Errors: {summary['error_count']}")
    print(f"Warnings: {summary['warning_count']}")
    print(f"Fields detected: {summary['detected_fields']}")

    if summary['errors']:
        print("\nFirst 5 errors:")
        for err in summary['errors'][:5]:
            print(f"  - {err}")

    if summary['warnings']:
        print("\nFirst 5 warnings:")
        for warn in summary['warnings'][:5]:
            print(f"  - {warn}")

    # --- Step 4: Basic assertions ---
    assert summary['total_records'] > 0, "No records were parsed"