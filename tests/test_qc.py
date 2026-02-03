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