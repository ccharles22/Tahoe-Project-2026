"""
Quality Control validation for parsed experimental data.
"""

from typing import Dict, List, Any, Tuple
from parsing.config import (
    REQUIRED_FIELDS, 
    VALIDATION_RULES, 
    ERROR_THRESHOLDS,
    WARNING_THRESHOLDS
)

class QualityControl:
    """Quality control validator for experimental records."""
    
    def __init__(self, config: Dict = None):
        """
        Initialize QC validator.
        
        Args:
            config: Optional custom configuration (defaults to parsing.config)
        """
        self.required_fields = REQUIRED_FIELDS
        self.validation_rules = VALIDATION_RULES
        self.error_thresholds = ERROR_THRESHOLDS
        self.warning_thresholds = WARNING_THRESHOLDS
        
        # Override with custom config if provided
        if config:
            self.validation_rules.update(config)
    
    def validate_record(self, record: Dict[str, Any], row_num: int) -> Tuple[List[str], List[str]]:
        """
        Validate a single record.
        
        Args:
            record: Record dictionary to validate
            row_num: Row number for error reporting
            
        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        
        # Check required fields
        missing = self._check_required_fields(record)
        if missing:
            errors.append(f"Row {row_num}: Missing required fields: {', '.join(missing)}")
        
        # Check data types
        type_errors = self._validate_types(record, row_num)
        errors.extend(type_errors)
        
        # Check value ranges (generates warnings)
        range_warnings = self._validate_ranges(record, row_num)
        warnings.extend(range_warnings)
        
        # Validate DNA sequence
        seq_errors, seq_warnings = self._validate_sequence(record, row_num)
        errors.extend(seq_errors)
        warnings.extend(seq_warnings)
        
        return errors, warnings
    
    def _check_required_fields(self, record: Dict[str, Any]) -> List[str]:
        """
        Check if all required fields are present and non-empty.
        
        Args:
            record: Record to check
            
        Returns:
            List of missing field names
        """
        missing = []
        
        for field in self.required_fields:
            if field not in record:
                missing.append(field)
            elif record[field] is None or record[field] == '':
                missing.append(field)
        
        return missing
    
    def _validate_types(self, record: Dict[str, Any], row_num: int) -> List[str]:
        """
        Validate data types for key fields.
        
        Args:
            record: Record to validate
            row_num: Row number
            
        Returns:
            List of error messages
        """
        errors = []
        
        # Variant index should be integer
        if 'variant_index' in record:
            try:
                int(record['variant_index'])
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: variant_index must be an integer, got '{record['variant_index']}'")
        
        # Generation should be integer
        if 'generation' in record:
            try:
                int(record['generation'])
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: generation must be an integer, got '{record['generation']}'")
        
        # Parent variant index (if present) should be integer or None
        if 'parent_variant_index' in record and record['parent_variant_index'] not in [None, '', 'NULL']:
            try:
                int(record['parent_variant_index'])
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: parent_variant_index must be an integer or NULL, got '{record['parent_variant_index']}'")
        
        # DNA yield should be numeric
        if 'dna_yield' in record:
            try:
                float(record['dna_yield'])
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: dna_yield must be numeric, got '{record['dna_yield']}'")
        
        # Protein yield should be numeric
        if 'protein_yield' in record:
            try:
                float(record['protein_yield'])
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: protein_yield must be numeric, got '{record['protein_yield']}'")
        
        return errors
    
    def _validate_ranges(self, record: Dict[str, Any], row_num: int) -> List[str]:
        """
        Validate value ranges (generates warnings, not errors).
        
        Args:
            record: Record to validate
            row_num: Row number
            
        Returns:
            List of warning messages
        """
        warnings = []
        
        # Check DNA yield
        if 'dna_yield' in record:
            try:
                dna_yield = float(record['dna_yield'])
                
                if dna_yield < self.validation_rules['yield_min_warning']:
                    warnings.append(f"Row {row_num}: Negative or very low DNA yield ({dna_yield}) - may indicate experimental error")
                
                if dna_yield > self.validation_rules['yield_max_warning']:
                    warnings.append(f"Row {row_num}: Extremely high DNA yield ({dna_yield}) - may indicate measurement error")
            except (ValueError, TypeError):
                pass  # Type error already caught in _validate_types
        
        # Check protein yield
        if 'protein_yield' in record:
            try:
                protein_yield = float(record['protein_yield'])
                
                if protein_yield < self.validation_rules['yield_min_warning']:
                    warnings.append(f"Row {row_num}: Negative or very low protein yield ({protein_yield}) - may indicate experimental error")
                
                if protein_yield > self.validation_rules['yield_max_warning']:
                    warnings.append(f"Row {row_num}: Extremely high protein yield ({protein_yield}) - may indicate measurement error")
            except (ValueError, TypeError):
                pass
        
        return warnings
    
    def _validate_sequence(self, record: Dict[str, Any], row_num: int) -> Tuple[List[str], List[str]]:
        """
        Validate DNA sequence.
        
        Args:
            record: Record to validate
            row_num: Row number
            
        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []
        
        if 'assembled_dna_sequence' not in record:
            return errors, warnings
        
        sequence = record['assembled_dna_sequence']
        
        # Check if empty
        if not sequence or sequence == '':
            errors.append(f"Row {row_num}: DNA sequence is empty")
            return errors, warnings
        
        # Check sequence length
        seq_len = len(sequence)
        
        if seq_len < self.validation_rules['sequence_min_length']:
            warnings.append(f"Row {row_num}: DNA sequence is very short ({seq_len} bp) - may be incomplete")
        
        if seq_len > self.validation_rules['sequence_max_length']:
            warnings.append(f"Row {row_num}: DNA sequence is very long ({seq_len} bp) - may include vector sequence")
        
        # Check for invalid characters
        allowed_chars = self.validation_rules['allowed_dna_chars']
        invalid_chars = set(sequence) - allowed_chars
        
        if invalid_chars:
            errors.append(f"Row {row_num}: DNA sequence contains invalid characters: {', '.join(sorted(invalid_chars))}")
        
        # Check if divisible by 3 (frameshift warning)
        if seq_len % 3 != 0:
            warnings.append(f"Row {row_num}: DNA sequence length ({seq_len}) not divisible by 3 - may cause frameshift")
        
        return errors, warnings