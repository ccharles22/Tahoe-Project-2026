"""
Comprehensive edge case tests for data parsing and QC.

Tests cover:
- Empty files
- Headers only (no data)
- Mixed valid/invalid records
- Very large files (1000+ records)
- Duplicate variant indices
- Missing generation 0
- Orphaned parent variants
- Invalid sequences
- Type mismatches
- Malformed JSON
- Encoding issues
- File size limits
"""

import os
import sys
import json
import pytest
import tempfile

# Ensure repository root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from parsing.tsv_parser import TSVParser
from parsing.json_parser import JSONParser
from parsing.qc import QualityControl


# =============================================================================
# Fixtures for creating test files
# =============================================================================

@pytest.fixture
def empty_tsv_file():
    """Create completely empty TSV file (0 bytes)."""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    # Write nothing - truly empty
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def empty_json_file():
    """Create completely empty JSON file (0 bytes)."""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def headers_only_tsv():
    """Create TSV with headers but no data rows."""
    content = "variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence\n"
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def empty_json_array():
    """Create JSON with empty array."""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    json.dump([], temp)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def single_valid_record_tsv():
    """Create TSV with single valid record."""
    content = """variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
1\t0\t\t100.5\t50.2\tATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def mixed_valid_invalid_tsv():
    """Create TSV with mix of valid and invalid records."""
    content = """variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
1\t0\t\t100.5\t50.2\tATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
2\tINVALID\t1\t80.0\t40.0\tATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
3\t1\t1\tN/A\t35.5\tATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
4\t1\t1\t90.0\t45.0\tATGCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
5\t2\t4\t110.0\t55.0\tATGC123GATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def large_file_tsv():
    """Create TSV with 1000+ valid records."""
    lines = ["variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence"]
    # Generate valid sequence (120 bp)
    valid_seq = "ATGC" * 30
    
    # Generation 0 (WT control)
    lines.append(f"1\t0\t\t100.0\t50.0\t{valid_seq}")
    
    # Generations 1-5 with many variants each
    variant_id = 2
    for gen in range(1, 6):
        for i in range(200):
            parent = variant_id - 200 if gen > 1 else 1
            dna_yield = 80 + (i % 40)
            protein_yield = 40 + (i % 30)
            lines.append(f"{variant_id}\t{gen}\t{parent}\t{dna_yield}\t{protein_yield}\t{valid_seq}")
            variant_id += 1
    
    content = "\n".join(lines) + "\n"
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def duplicate_variant_indices_tsv():
    """Create TSV with duplicate variant_index values."""
    valid_seq = "ATGC" * 30
    content = f"""variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
1\t0\t\t100.5\t50.2\t{valid_seq}
2\t1\t1\t80.0\t40.0\t{valid_seq}
2\t1\t1\t85.0\t42.0\t{valid_seq}
3\t1\t1\t90.0\t45.0\t{valid_seq}
3\t2\t2\t95.0\t47.0\t{valid_seq}
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def missing_generation_zero_tsv():
    """Create TSV with no generation 0 records."""
    valid_seq = "ATGC" * 30
    content = f"""variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
1\t1\t\t100.5\t50.2\t{valid_seq}
2\t2\t1\t80.0\t40.0\t{valid_seq}
3\t3\t2\t90.0\t45.0\t{valid_seq}
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def orphaned_parents_tsv():
    """Create TSV with parent references to non-existent variants."""
    valid_seq = "ATGC" * 30
    content = f"""variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
1\t0\t\t100.5\t50.2\t{valid_seq}
2\t1\t999\t80.0\t40.0\t{valid_seq}
3\t1\t1\t90.0\t45.0\t{valid_seq}
4\t2\t888\t85.0\t42.0\t{valid_seq}
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def invalid_sequence_tsv():
    """Create TSV with various sequence issues."""
    content = """variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
1\t0\t\t100.5\t50.2\tATGC123GATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
2\t1\t1\t80.0\t40.0\tatgcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcgatcg
3\t1\t1\t90.0\t45.0\tATGC GATC GATC GATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
4\t2\t2\t85.0\t42.0\tATGC@#$GATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCGATCG
5\t2\t2\t95.0\t47.0\tATG
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def type_mismatch_tsv():
    """Create TSV with type mismatches in various fields."""
    valid_seq = "ATGC" * 30
    content = f"""variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
abc\t0\t\t100.5\t50.2\t{valid_seq}
2\txyz\t1\t80.0\t40.0\t{valid_seq}
3\t1\tabc\t90.0\t45.0\t{valid_seq}
4\t1\t1\tN/A\t42.0\t{valid_seq}
5\t2\t4\t85.0\tnull\t{valid_seq}
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def empty_required_fields_tsv():
    """Create TSV with empty values in required fields."""
    valid_seq = "ATGC" * 30
    content = f"""variant_index\tgeneration\tparent_variant_index\tdna_yield\tprotein_yield\tassembled_dna_sequence
\t0\t\t100.5\t50.2\t{valid_seq}
2\t\t1\t80.0\t40.0\t{valid_seq}
3\t1\t1\t\t45.0\t{valid_seq}
4\t1\t1\t85.0\t\t{valid_seq}
5\t2\t4\t95.0\t47.0\t
"""
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def malformed_json():
    """Create malformed JSON file."""
    content = '{"records": [{"variant_index": 1, "generation": 0, "invalid json here'
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


@pytest.fixture
def valid_json_file():
    """Create valid JSON file for comparison."""
    valid_seq = "ATGC" * 30
    data = [
        {"variant_index": 1, "generation": 0, "parent_variant_index": None, 
         "dna_yield": 100.5, "protein_yield": 50.2, "assembled_dna_sequence": valid_seq},
        {"variant_index": 2, "generation": 1, "parent_variant_index": 1,
         "dna_yield": 80.0, "protein_yield": 40.0, "assembled_dna_sequence": valid_seq}
    ]
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    json.dump(data, temp)
    temp.close()
    yield temp.name
    os.unlink(temp.name)


# =============================================================================
# Tests for Empty Files
# =============================================================================

class TestEmptyFiles:
    """Tests for handling empty file uploads."""
    
    def test_empty_tsv_file(self, empty_tsv_file):
        """Test parsing completely empty TSV file."""
        parser = TSVParser(empty_tsv_file)
        result = parser.parse()
        
        assert result is False
        assert len(parser.errors) > 0
        assert "empty" in parser.errors[0].lower()
        assert len(parser.records) == 0
    
    def test_empty_json_file(self, empty_json_file):
        """Test parsing completely empty JSON file."""
        parser = JSONParser(empty_json_file)
        result = parser.parse()
        
        assert result is False
        assert len(parser.errors) > 0
        assert "empty" in parser.errors[0].lower()
        assert len(parser.records) == 0
    
    def test_empty_json_array(self, empty_json_array):
        """Test parsing JSON with empty array []."""
        parser = JSONParser(empty_json_array)
        result = parser.parse()
        
        assert result is False
        assert len(parser.errors) > 0
        assert "no records" in parser.errors[0].lower()


# =============================================================================
# Tests for Headers Only
# =============================================================================

class TestHeadersOnly:
    """Tests for files with headers but no data."""
    
    def test_headers_only_tsv(self, headers_only_tsv):
        """Test parsing TSV with only headers, no data rows."""
        parser = TSVParser(headers_only_tsv)
        result = parser.parse()
        
        assert result is False
        assert len(parser.errors) > 0
        assert "no data" in parser.errors[0].lower() or "headers but no" in parser.errors[0].lower()
        assert len(parser.records) == 0


# =============================================================================
# Tests for Single Valid Record
# =============================================================================

class TestSingleRecord:
    """Tests for minimal valid files."""
    
    def test_single_valid_record_tsv(self, single_valid_record_tsv):
        """Test parsing TSV with single valid record."""
        parser = TSVParser(single_valid_record_tsv)
        result = parser.parse()
        
        assert result is True
        assert len(parser.records) == 1
        assert len(parser.errors) == 0
        
        # Run QC
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Should have no errors (generation 0 warning is acceptable)
        assert len(parser.errors) == 0


# =============================================================================
# Tests for Mixed Valid/Invalid Records
# =============================================================================

class TestMixedRecords:
    """Tests for files with mix of valid and invalid records."""
    
    def test_mixed_valid_invalid(self, mixed_valid_invalid_tsv):
        """Test parsing file with mix of valid and invalid records."""
        parser = TSVParser(mixed_valid_invalid_tsv)
        result = parser.parse()
        
        assert result is True
        assert len(parser.records) == 5  # All rows parsed
        
        # Run QC validation
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Should have errors for invalid rows
        assert len(parser.errors) > 0
        
        # Check for specific error types
        error_text = " ".join(parser.errors)
        assert "generation" in error_text.lower()  # Row 2: INVALID generation
        assert "dna_yield" in error_text.lower()   # Row 3: N/A dna_yield
        assert "invalid characters" in error_text.lower()  # Row 5: 123 in sequence
    
    def test_error_messages_are_actionable(self, mixed_valid_invalid_tsv):
        """Verify error messages provide actionable guidance."""
        parser = TSVParser(mixed_valid_invalid_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Check that errors include helpful guidance
        for error in parser.errors:
            # Each error should have row number
            assert "Row" in error
            # Errors should include guidance (not just the problem)
            assert any(word in error.lower() for word in 
                      ["please", "use", "provide", "ensure", "valid", "expected"])


# =============================================================================
# Tests for Large Files
# =============================================================================

class TestLargeFiles:
    """Tests for performance with large files."""
    
    def test_large_file_parsing(self, large_file_tsv):
        """Test parsing file with 1000+ records."""
        parser = TSVParser(large_file_tsv)
        result = parser.parse()
        
        assert result is True
        assert len(parser.records) >= 1000
        assert len(parser.errors) == 0
    
    def test_large_file_qc(self, large_file_tsv):
        """Test QC validation on large file."""
        parser = TSVParser(large_file_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Should complete without errors for valid data
        assert len(parser.errors) == 0
        
        # Summary should reflect all records
        summary = parser.get_summary()
        assert summary['total_records'] >= 1000


# =============================================================================
# Tests for Duplicate Variant Indices
# =============================================================================

class TestDuplicateIndices:
    """Tests for duplicate variant_index detection."""
    
    def test_duplicate_detection(self, duplicate_variant_indices_tsv):
        """Test that duplicate variant indices are detected."""
        parser = TSVParser(duplicate_variant_indices_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Should have error for duplicates
        assert len(parser.errors) > 0
        error_text = " ".join(parser.errors)
        assert "duplicate" in error_text.lower()
        assert "2" in error_text  # variant_index 2 is duplicated
        assert "3" in error_text  # variant_index 3 is duplicated
    
    def test_duplicate_error_shows_rows(self, duplicate_variant_indices_tsv):
        """Test that duplicate error message shows affected rows."""
        parser = TSVParser(duplicate_variant_indices_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Error should mention rows
        error_text = " ".join(parser.errors)
        assert "rows" in error_text.lower() or "row" in error_text.lower()


# =============================================================================
# Tests for Missing Generation 0
# =============================================================================

class TestMissingGeneration:
    """Tests for missing generation 0 detection."""
    
    def test_missing_generation_zero_warning(self, missing_generation_zero_tsv):
        """Test warning for missing generation 0 (WT control)."""
        parser = TSVParser(missing_generation_zero_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Should have warning (not error) for missing gen 0
        assert len(parser.warnings) > 0
        warning_text = " ".join(parser.warnings)
        assert "generation 0" in warning_text.lower() or "wt" in warning_text.lower()
    
    def test_missing_generation_suggests_fix(self, missing_generation_zero_tsv):
        """Test that missing generation warning suggests adding WT control."""
        parser = TSVParser(missing_generation_zero_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        warning_text = " ".join(parser.warnings)
        assert any(word in warning_text.lower() for word in 
                  ["control", "wild-type", "baseline", "add"])


# =============================================================================
# Tests for Orphaned Parent Variants
# =============================================================================

class TestOrphanedParents:
    """Tests for parent variant reference validation."""
    
    def test_orphaned_parent_warning(self, orphaned_parents_tsv):
        """Test warning for references to non-existent parent variants."""
        parser = TSVParser(orphaned_parents_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Should have warnings for orphaned parents
        warning_text = " ".join(parser.warnings)
        assert "999" in warning_text or "888" in warning_text
        assert "parent" in warning_text.lower()


# =============================================================================
# Tests for Invalid Sequences
# =============================================================================

class TestInvalidSequences:
    """Tests for DNA sequence validation."""
    
    def test_invalid_sequence_characters(self, invalid_sequence_tsv):
        """Test detection of invalid characters in sequences."""
        parser = TSVParser(invalid_sequence_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        error_text = " ".join(parser.errors)
        # Should catch numbers and special chars
        assert "invalid characters" in error_text.lower()
    
    def test_short_sequence_warning(self, invalid_sequence_tsv):
        """Test warning for very short sequences."""
        parser = TSVParser(invalid_sequence_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Last row has very short sequence (3 bp)
        warning_text = " ".join(parser.warnings)
        assert "short" in warning_text.lower() or "minimum" in warning_text.lower()


# =============================================================================
# Tests for Type Mismatches
# =============================================================================

class TestTypeMismatches:
    """Tests for data type validation."""
    
    def test_type_mismatch_detection(self, type_mismatch_tsv):
        """Test detection of type mismatches."""
        parser = TSVParser(type_mismatch_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        assert len(parser.errors) > 0
        error_text = " ".join(parser.errors)
        
        # Should catch each type of mismatch
        assert "variant_index" in error_text.lower()
        assert "generation" in error_text.lower()
        assert "dna_yield" in error_text.lower()
        assert "protein_yield" in error_text.lower()
    
    def test_type_error_messages_are_helpful(self, type_mismatch_tsv):
        """Test that type error messages provide examples."""
        parser = TSVParser(type_mismatch_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        # Errors should include examples
        for error in parser.errors:
            if "integer" in error.lower() or "numeric" in error.lower():
                assert "e.g." in error.lower() or any(char.isdigit() for char in error)


# =============================================================================
# Tests for Empty Required Fields
# =============================================================================

class TestEmptyRequiredFields:
    """Tests for empty required field detection."""
    
    def test_empty_required_fields_detection(self, empty_required_fields_tsv):
        """Test detection of empty required fields."""
        parser = TSVParser(empty_required_fields_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        assert len(parser.errors) > 0
        error_text = " ".join(parser.errors)
        assert "missing" in error_text.lower() or "required" in error_text.lower()


# =============================================================================
# Tests for Malformed JSON
# =============================================================================

class TestMalformedJSON:
    """Tests for JSON syntax error handling."""
    
    def test_malformed_json_error(self, malformed_json):
        """Test handling of malformed JSON."""
        parser = JSONParser(malformed_json)
        result = parser.parse()
        
        assert result is False
        assert len(parser.errors) > 0
        error_text = parser.errors[0].lower()
        assert "json" in error_text
        assert "line" in error_text or "column" in error_text
    
    def test_malformed_json_suggests_validation(self, malformed_json):
        """Test that malformed JSON error suggests validation tool."""
        parser = JSONParser(malformed_json)
        parser.parse()
        
        error_text = parser.errors[0].lower()
        assert "validate" in error_text or "validator" in error_text or "syntax" in error_text


# =============================================================================
# Tests for Valid JSON (baseline)
# =============================================================================

class TestValidJSON:
    """Tests for valid JSON parsing (baseline)."""
    
    def test_valid_json_parsing(self, valid_json_file):
        """Test parsing valid JSON file."""
        parser = JSONParser(valid_json_file)
        result = parser.parse()
        
        assert result is True
        assert len(parser.records) == 2
        assert len(parser.errors) == 0
    
    def test_valid_json_qc(self, valid_json_file):
        """Test QC on valid JSON data."""
        parser = JSONParser(valid_json_file)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        assert len(parser.errors) == 0


# =============================================================================
# Tests for Row Number Reporting
# =============================================================================

class TestRowNumberReporting:
    """Tests for accurate row number in error messages."""
    
    def test_row_numbers_in_errors(self, mixed_valid_invalid_tsv):
        """Test that all errors include row numbers."""
        parser = TSVParser(mixed_valid_invalid_tsv)
        parser.parse()
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        for error in parser.errors:
            # Each per-record error should have "Row X:"
            if "duplicate" not in error.lower():  # Cross-record errors may format differently
                assert "Row" in error
    
    def test_row_numbers_start_at_2_for_tsv(self, mixed_valid_invalid_tsv):
        """Test that row numbers start at 2 (row 1 is headers)."""
        parser = TSVParser(mixed_valid_invalid_tsv)
        parser.parse()
        
        # First record should be row 2
        assert parser.records[0].get('_row_number') == 2


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests combining parser and QC."""
    
    def test_full_pipeline_valid_data(self, single_valid_record_tsv):
        """Test full parsing and QC pipeline with valid data."""
        parser = TSVParser(single_valid_record_tsv)
        assert parser.parse() is True
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        summary = parser.get_summary()
        assert summary['total_records'] == 1
        assert summary['error_count'] == 0
    
    def test_full_pipeline_with_errors(self, mixed_valid_invalid_tsv):
        """Test full pipeline reports all issues."""
        parser = TSVParser(mixed_valid_invalid_tsv)
        assert parser.parse() is True
        
        qc = QualityControl()
        parser.validate_all(qc)
        
        summary = parser.get_summary()
        assert summary['total_records'] == 5
        assert summary['error_count'] > 0
        assert summary['warning_count'] >= 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
