"""
Performance tests for data parsing and QC pipeline.

Tests large file handling, batch database operations, and memory efficiency.
"""

import os
import sys
import time
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.parsing.tsv_parser import TSVParser
from app.services.parsing.json_parser import JSONParser
from app.services.parsing.qc import QualityControl
from app.services.parsing.utils import safe_int, safe_float, prepare_variant_data


class TestLargeFileParsing:
    """Tests for parsing performance with large files."""
    
    @pytest.fixture
    def large_tsv_file(self) -> str:
        """Create a large TSV file with 10,000 records."""
        content = "variant_index\tgeneration\tparent_variant_index\tassembled_dna_sequence\tdna_yield\tprotein_yield\n"
        for i in range(10000):
            parent = i - 1 if i > 0 else 0
            seq = "ATCGATCG" * 10
            content += f"{i}\t{i % 5}\t{parent}\t{seq}\t{100.0 + i * 0.01:.2f}\t{50.0 + i * 0.005:.3f}\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            f.write(content)
            return f.name
    
    @pytest.fixture
    def large_json_file(self) -> str:
        """Create a large JSON file with 5,000 records."""
        import json
        records = []
        for i in range(5000):
            parent = i - 1 if i > 0 else 0
            seq = "ATCGATCG" * 10
            records.append({
                "variant_index": i,
                "generation": i % 5,
                "parent_variant_index": parent,
                "assembled_dna_sequence": seq,
                "dna_yield": 100.0 + i * 0.01,
                "protein_yield": 50.0 + i * 0.005
            })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(records, f)
            return f.name
    
    def test_large_tsv_parsing_time(self, large_tsv_file: str) -> None:
        """Test that 10,000 record TSV parses in under 5 seconds."""
        parser = TSVParser(large_tsv_file)
        
        start_time = time.time()
        success = parser.parse()
        parse_time = time.time() - start_time
        
        assert success, f"Parsing failed: {parser.errors}"
        assert len(parser.records) == 10000
        assert parse_time < 5.0, f"Parsing took {parse_time:.2f}s, expected < 5s"
        
        # Clean up
        os.unlink(large_tsv_file)
    
    def test_large_json_parsing_time(self, large_json_file: str) -> None:
        """Test that 5,000 record JSON parses in under 3 seconds."""
        parser = JSONParser(large_json_file)
        
        start_time = time.time()
        success = parser.parse()
        parse_time = time.time() - start_time
        
        assert success, f"Parsing failed: {parser.errors}"
        assert len(parser.records) == 5000
        assert parse_time < 3.0, f"Parsing took {parse_time:.2f}s, expected < 3s"
        
        # Clean up
        os.unlink(large_json_file)


class TestQCPerformance:
    """Tests for QC validation performance."""
    
    def test_qc_large_dataset(self) -> None:
        """Test QC validation on 10,000 records completes in reasonable time."""
        records = []
        for i in range(10000):
            parent = i - 1 if i > 0 else 0
            records.append({
                "variant_index": i,
                "generation": i % 5,
                "parent_variant_index": parent,
                "assembled_dna_sequence": "ATCGATCG" * 10,
                "dna_yield": 100.0 + i * 0.01,
                "protein_yield": 50.0
            })
        
        qc = QualityControl()
        
        start_time = time.time()
        all_errors = []
        all_warnings = []
        for idx, record in enumerate(records):
            errors, warnings = qc.validate_record(record, idx)
            all_errors.extend(errors)
            all_warnings.extend(warnings)
        
        # Cross-record validation
        cross_errors, cross_warnings = qc.validate_cross_record(records)
        all_errors.extend(cross_errors)
        all_warnings.extend(cross_warnings)
        
        qc_time = time.time() - start_time
        
        assert qc_time < 10.0, f"QC took {qc_time:.2f}s, expected < 10s"
        # Should have no errors for valid data
        assert len(all_errors) == 0, f"Unexpected errors: {all_errors[:5]}"


class TestUtilityPerformance:
    """Tests for utility function performance."""
    
    def test_safe_int_bulk_conversions(self) -> None:
        """Test safe_int handles bulk conversions efficiently."""
        values = [str(i) for i in range(100000)]
        
        start_time = time.time()
        results = [safe_int(v) for v in values]
        convert_time = time.time() - start_time
        
        assert len(results) == 100000
        assert all(r == i for i, r in enumerate(results))
        assert convert_time < 1.0, f"Conversions took {convert_time:.2f}s"
    
    def test_safe_float_bulk_conversions(self) -> None:
        """Test safe_float handles bulk conversions efficiently."""
        values = [f"{i}.{i % 10}" for i in range(100000)]
        
        start_time = time.time()
        results = [safe_float(v) for v in values]
        convert_time = time.time() - start_time
        
        assert len(results) == 100000
        assert convert_time < 1.0, f"Conversions took {convert_time:.2f}s"
    
    def test_safe_conversions_with_invalid_values(self) -> None:
        """Test safe conversions handle mixed valid/invalid values efficiently."""
        values = [
            str(i) if i % 3 != 0 else 'NULL'
            for i in range(50000)
        ]
        
        start_time = time.time()
        results = [safe_int(v) for v in values]
        convert_time = time.time() - start_time
        
        # Count None results for NULL values
        none_count = sum(1 for r in results if r is None)
        expected_nulls = len([v for v in values if v == 'NULL'])
        
        assert none_count == expected_nulls
        assert convert_time < 1.0, f"Conversions took {convert_time:.2f}s"


class TestMemoryEfficiency:
    """Tests for memory efficiency with large datasets."""
    
    def test_parser_memory_handling(self) -> None:
        """Test that parser doesn't duplicate data unnecessarily."""
        # Create a moderately large dataset in memory
        content = "variant_index\tgeneration\tassembled_dna_sequence\n"
        for i in range(5000):
            seq = "A" * 100  # 100 character sequences
            content += f"{i}\t{i % 5}\t{seq}\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            f.write(content)
            filepath = f.name
        
        try:
            parser = TSVParser(filepath)
            success = parser.parse()
            
            assert success
            assert len(parser.records) == 5000
            
            # Verify data integrity
            for i, record in enumerate(parser.records[:10]):
                assert record['variant_index'] == str(i)
                assert len(record['assembled_dna_sequence']) == 100
        finally:
            os.unlink(filepath)


class TestBatchOperations:
    """Tests for batch database operation performance."""
    
    def test_prepare_variant_data_batch(self) -> None:
        """Test prepare_variant_data handles batch preparation efficiently."""
        records = []
        for i in range(10000):
            records.append({
                "variant_index": str(i),
                "generation": str(i % 5),
                "parent_variant_index": str(i - 1) if i > 0 else "0",
                "assembled_dna_sequence": "ATCG" * 20,
                "dna_yield": str(100.0 + i * 0.01),
                "protein_yield": str(50.0),
                "extra_field": f"metadata_{i}"
            })
        
        start_time = time.time()
        prepared = []
        for record in records:
            core_data = {k: v for k, v in record.items() 
                        if k in ['variant_index', 'generation', 'parent_variant_index',
                                'assembled_dna_sequence', 'dna_yield', 'protein_yield']}
            metadata = {k: v for k, v in record.items() if k not in core_data}
            
            data = prepare_variant_data(record, 1, core_data, metadata)
            prepared.append(data)
        
        prep_time = time.time() - start_time
        
        assert len(prepared) == 10000
        assert prep_time < 2.0, f"Preparation took {prep_time:.2f}s"
        
        # Verify data integrity
        assert prepared[0]['variant_index'] == 0
        assert prepared[0]['experiment_id'] == 1
        assert prepared[9999]['variant_index'] == 9999
