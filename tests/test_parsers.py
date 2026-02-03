"""
Unit tests for parsers.
"""

import pytest
from parsing.tsv_parser import TSVParser
from parsing.json_parser import JSONParser
from parsing.qc import QualityControl


def test_tsv_delimiter_detection():
    """Test that TSV parser correctly detects tab delimiter."""
    parser = TSVParser("data/DE_BSU_Pol_Batch_1.tsv")

    with open("data/DE_BSU_Pol_Batch_1.tsv", "r") as f:
        first_line = f.readline()

    delimiter = parser._detect_delimiter(first_line)
    assert delimiter == "\t"


def test_tsv_parsing():
    """Test basic TSV parsing."""
    parser = TSVParser("data/DE_BSU_Pol_Batch_1.tsv")
    success = parser.parse()

    assert success is True
    assert len(parser.records) > 0
    assert len(parser.errors) == 0


def test_json_parsing():
    """Test basic JSON parsing."""
    parser = JSONParser("data/DE_BSU_Pol_Batch_1.json")
    success = parser.parse()

    assert success is True
    assert len(parser.records) > 0
    assert len(parser.errors) == 0


def test_full_tsv_workflow():
    parser = TSVParser("data/DE_BSU_Pol_Batch_1.tsv")
    success = parser.parse()

    if not success:
        print("\nPARSER ERRORS:")
        for err in parser.errors:
            print(err)

    assert success is True

    qc = QualityControl()
    parser.validate_all(qc)

    summary = parser.get_summary()

    print("\n=== PARSING SUMMARY ===")
    print(f"Total records: {summary['total_records']}")
    print(f"Errors: {summary['error_count']}")
    print(f"Warnings: {summary['warning_count']}")
    print(f"Fields detected: {summary['detected_fields']}")

    assert summary["total_records"] > 0