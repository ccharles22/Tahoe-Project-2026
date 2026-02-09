"""
Abstract base class for data file parsers.

Provides common interface and utility methods for TSV, CSV, and JSON parsers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Set, Optional
from parsing.config import FIELD_MAPPING, REQUIRED_FIELDS, OPTIONAL_FIELDS


class BaseParser(ABC):
    """
    Abstract base class for data parsers.
    
    Attributes:
        filepath: Path to the file being parsed
        records: List of parsed record dictionaries
        errors: List of validation error messages
        warnings: List of validation warning messages
        detected_fields: Set of field names found in the file
        metadata: Additional file-level metadata
    """

    def __init__(self, filepath: str) -> None:
        self.filepath: str = filepath
        self.records: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.detected_fields: Set[str] = set()
        self.metadata: Dict[str, Any] = {}

    @abstractmethod
    def parse(self) -> bool:
        """Parse the file and populate self.records."""
        pass

    def normalize_field_names(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize field names to standard format using FIELD_MAPPING.
        
        Args:
            record: Raw record dictionary with potentially varied field names
            
        Returns:
            Dictionary with standardized field names
        """
        normalized: Dict[str, Any] = {}

        for key, value in record.items():
            standard_name: Optional[str] = None

            if key in FIELD_MAPPING:
                standard_name = key
            else:
                for std_name, alternates in FIELD_MAPPING.items():
                    if key in alternates:
                        standard_name = std_name
                        break

            final_key = standard_name if standard_name else key
            normalized[final_key] = value
            self.detected_fields.add(final_key)

        return normalized

    def extract_metadata(self, record: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extract core fields and additional metadata from a record.
        
        Args:
            record: Parsed record dictionary
            
        Returns:
            Tuple of (core_data dict, metadata dict)
        """
        all_known_fields: Set[str] = set(REQUIRED_FIELDS + OPTIONAL_FIELDS)

        core_data = {k: v for k, v in record.items() if k in all_known_fields}
        metadata = {k: v for k, v in record.items() if k not in all_known_fields}

        return core_data, metadata

    def validate_all(self, qc_validator) -> None:
        """
        Run QC validation on all parsed records.

        Args:
            qc_validator: QualityControl instance
        """
        # If the QC validator supports computing dataset-level thresholds
        # (data-driven mode), compute them before performing per-record checks.
        try:
            if getattr(qc_validator, "percentile_mode", False):
                qc_validator.compute_thresholds_from_records(self.records)
        except Exception:
            # Any error computing thresholds shouldn't stop per-record validation
            pass

        # Per-record validation
        for idx, record in enumerate(self.records):
            errors, warnings = qc_validator.validate_record(record, idx)
            self.errors.extend(errors)
            self.warnings.extend(warnings)

        # Cross-record validation
        try:
            cross_errors, cross_warnings = qc_validator.validate_cross_record(self.records)
            self.errors.extend(cross_errors)
            self.warnings.extend(cross_warnings)
        except AttributeError:
            # Validator does not implement cross-record checks; ignore
            pass

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_records": len(self.records),
            "detected_fields": sorted(self.detected_fields),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }
