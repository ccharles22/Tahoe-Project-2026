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
    
    def __init__(self, config: Dict = None, *, percentile_mode: bool = False, percentile_low: float = 5.0, percentile_high: float = 95.0):
        """
        Initialize QC validator.
        
        Args:
            config: Optional custom configuration (defaults to parsing.config)
        """
        self.required_fields = REQUIRED_FIELDS
        self.validation_rules = VALIDATION_RULES
        self.error_thresholds = ERROR_THRESHOLDS
        self.warning_thresholds = WARNING_THRESHOLDS
        # Percentile-based dataset-driven thresholds
        self.percentile_mode = bool(percentile_mode)
        self.percentile_low = float(percentile_low)
        self.percentile_high = float(percentile_high)

        # Override with custom config if provided
        if config:
            self.validation_rules.update(config)

        # Per-metric thresholds (computed or from config). Initialize from config fallbacks.
        self.dna_yield_min_warning = self.validation_rules.get('dna_yield_min_warning', self.validation_rules.get('yield_min_warning'))
        self.dna_yield_max_warning = self.validation_rules.get('dna_yield_max_warning', self.validation_rules.get('yield_max_warning'))
        self.protein_yield_min_warning = self.validation_rules.get('protein_yield_min_warning', self.validation_rules.get('yield_min_warning'))
        self.protein_yield_max_warning = self.validation_rules.get('protein_yield_max_warning', self.validation_rules.get('yield_max_warning'))
    
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
        
        # Check DNA yield (use per-metric thresholds if available)
        if 'dna_yield' in record:
            try:
                dna_yield = float(record['dna_yield'])
                min_thr = getattr(self, 'dna_yield_min_warning', self.validation_rules.get('yield_min_warning'))
                max_thr = getattr(self, 'dna_yield_max_warning', self.validation_rules.get('yield_max_warning'))

                if min_thr is not None and dna_yield < min_thr:
                    warnings.append(f"Row {row_num}: Negative or very low DNA yield ({dna_yield}) - may indicate experimental error")

                if max_thr is not None and dna_yield > max_thr:
                    warnings.append(f"Row {row_num}: Extremely high DNA yield ({dna_yield}) - may indicate measurement error")
            except (ValueError, TypeError):
                pass  # Type error already caught in _validate_types
        
        # Check protein yield (use per-metric thresholds if available)
        if 'protein_yield' in record:
            try:
                protein_yield = float(record['protein_yield'])
                min_thr = getattr(self, 'protein_yield_min_warning', self.validation_rules.get('yield_min_warning'))
                max_thr = getattr(self, 'protein_yield_max_warning', self.validation_rules.get('yield_max_warning'))

                if min_thr is not None and protein_yield < min_thr:
                    warnings.append(f"Row {row_num}: Negative or very low protein yield ({protein_yield}) - may indicate experimental error")

                if max_thr is not None and protein_yield > max_thr:
                    warnings.append(f"Row {row_num}: Extremely high protein yield ({protein_yield}) - may indicate measurement error")
            except (ValueError, TypeError):
                pass
        
        return warnings

    def compute_thresholds_from_records(self, records: List[Dict[str, Any]]) -> None:
        """
        Compute per-metric thresholds from the dataset using percentiles.

        This sets dna_yield_min_warning/dna_yield_max_warning and
        protein_yield_min_warning/protein_yield_max_warning based on
        configured percentiles (percentile_low, percentile_high).
        If numpy is available it will be used; otherwise a small
        pure-Python percentile implementation is used.
        """
        def _percentile(arr, p):
            # arr: sorted list
            n = len(arr)
            if n == 0:
                return None
            if p <= 0:
                return arr[0]
            if p >= 100:
                return arr[-1]
            # linear interpolation
            k = (n - 1) * (p / 100.0)
            f = int(k)
            c = f + 1
            if c >= n:
                return arr[f]
            d0 = arr[f] * (c - k)
            d1 = arr[c] * (k - f)
            return d0 + d1

        dna_vals = []
        prot_vals = []
        for r in records:
            try:
                v = r.get('dna_yield')
                if v not in (None, '', 'NULL'):
                    dna_vals.append(float(v))
            except Exception:
                pass
            try:
                v = r.get('protein_yield')
                if v not in (None, '', 'NULL'):
                    prot_vals.append(float(v))
            except Exception:
                pass

        # compute percentiles
        if dna_vals:
            dna_vals_sorted = sorted(dna_vals)
            try:
                import numpy as _np
                low = float(_np.percentile(dna_vals_sorted, self.percentile_low))
                high = float(_np.percentile(dna_vals_sorted, self.percentile_high))
            except Exception:
                low = _percentile(dna_vals_sorted, self.percentile_low)
                high = _percentile(dna_vals_sorted, self.percentile_high)
            if low is not None:
                self.dna_yield_min_warning = low
            if high is not None:
                self.dna_yield_max_warning = high

        if prot_vals:
            prot_vals_sorted = sorted(prot_vals)
            try:
                import numpy as _np
                low = float(_np.percentile(prot_vals_sorted, self.percentile_low))
                high = float(_np.percentile(prot_vals_sorted, self.percentile_high))
            except Exception:
                low = _percentile(prot_vals_sorted, self.percentile_low)
                high = _percentile(prot_vals_sorted, self.percentile_high)
            if low is not None:
                self.protein_yield_min_warning = low
            if high is not None:
                self.protein_yield_max_warning = high

        # Optionally, keep generic fallback values too (left unchanged)
    
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
        if (
            self.warning_thresholds.get("frameshift_sequence", False)
            and seq_len % 3 != 0
        ):
            warnings.append(
                f"Row {row_num}: DNA sequence length ({seq_len}) not divisible by 3"
            )
        return errors, warnings

    def validate_cross_record(self, records: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """
        Perform cross-record validation (duplicates, lineage, generations).

        Args:
            records: List of all parsed records

        Returns:
            Tuple of (errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        # --- Duplicate variant indices ---
        variant_indices = [r.get("variant_index") for r in records if r.get("variant_index") is not None]
        duplicates = {idx for idx in variant_indices if variant_indices.count(idx) > 1}
        if duplicates:
            errors.append(f"Duplicate variant indices found: {sorted(duplicates)}")

        # --- Generation 0 exists ---
        generations = [r.get("generation") for r in records if r.get("generation") is not None]
        if generations and 0 not in generations:
            warnings.append("No generation 0 (WT control) records found")

        # --- Generation continuity ---
        if generations:
            unique_gens = sorted(set(generations))
            expected = list(range(min(unique_gens), max(unique_gens) + 1))
            missing_gens = set(expected) - set(unique_gens)
            if missing_gens:
                warnings.append(f"Missing generations: {sorted(missing_gens)}")

        # --- Orphaned parent variants ---
        all_variant_ids = {r.get("variant_index") for r in records if r.get("variant_index") is not None}

        for record in records:
            parent_id = record.get("parent_variant_index")
            gen = record.get("generation")
            row = record.get("_row_number", "?")

            # Skip generation 0 or missing parent
            if not parent_id or gen == 0:
                continue

            try:
                parent_id_int = int(parent_id)
                if parent_id_int not in all_variant_ids:
                    warnings.append(f"Row {row}: Parent variant {parent_id} not found in dataset")
            except (ValueError, TypeError):
                pass  # Already handled in per-record validation

        return errors, warnings