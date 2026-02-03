"""
Unit tests for quality control.
"""

import pytest
from parsing.qc import QualityControl


def test_missing_required_fields():
    """Test detection of missing required fields."""
    qc = QualityControl()
    
    # Record missing variant_index
    record = {
        'generation': 0,
        'assembled_dna_sequence': 'ATG' * 300,  # valid length
        'dna_yield': 100.0,
        'protein_yield': 50.0
    }
    
    errors, warnings = qc.validate_record(record, row_num=1)
    
    assert len(errors) > 0, "Should detect missing variant_index"
    assert 'variant_index' in errors[0], "Error should mention variant_index"


def test_invalid_data_types():
    """Test detection of invalid data types."""
    qc = QualityControl()
    
    record = {
        'variant_index': 'not_a_number',  # Should be int
        'generation': 0,
        'assembled_dna_sequence': 'ATG' * 300,
        'dna_yield': 100.0,
        'protein_yield': 50.0
    }
    
    errors, warnings = qc.validate_record(record, row_num=1)
    
    assert len(errors) > 0, "Should detect invalid variant_index type"


def test_negative_yield_warning():
    """Test that negative yields generate warnings."""
    qc = QualityControl()
    
    record = {
        'variant_index': 1,
        'generation': 0,
        'assembled_dna_sequence': 'ATG' * 300,  # valid length, no frameshift
        'dna_yield': -10.0,  # Negative
        'protein_yield': 50.0
    }
    
    errors, warnings = qc.validate_record(record, row_num=1)
    
    assert len(warnings) > 0, "Should generate warning for negative yield"
    assert len(errors) == 0, "Should not error on negative yield"


def test_invalid_dna_characters():
    """Test detection of invalid DNA characters."""
    qc = QualityControl()
    
    record = {
        'variant_index': 1,
        'generation': 0,
        'assembled_dna_sequence': 'ATGCXYZ' + ('ATG' * 300),  # Invalid chars included
        'dna_yield': 100.0,
        'protein_yield': 50.0
    }
    
    errors, warnings = qc.validate_record(record, row_num=1)
    
    assert len(errors) > 0, "Should detect invalid DNA characters"


def test_duplicate_variant_indices():
    """Test detection of duplicate variant indices."""
    qc = QualityControl()
    records = [
        {'variant_index': 1, 'generation': 0},
        {'variant_index': 1, 'generation': 1},  # Duplicate
    ]
    errors, warnings = qc.validate_cross_record(records)
    assert len(errors) > 0, "Should detect duplicate variant indices"
    assert '1' in errors[0], "Error should mention duplicate ID"


def test_orphaned_parent():
    """Test detection of orphaned parent indices."""
    qc = QualityControl()
    records = [
        {'variant_index': 1, 'generation': 0, 'parent_variant_index': None},
        {'variant_index': 2, 'generation': 1, 'parent_variant_index': 99},  # Parent doesn't exist
    ]
    errors, warnings = qc.validate_cross_record(records)
    assert len(warnings) > 0, "Should warn about orphaned parent"
    assert "Parent variant 99" in warnings[0]