from abc import ABC, abstractmethod
from typing import Dict, Any
from parsing.config import FIELD_MAPPING, REQUIRED_FIELDS, OPTIONAL_FIELDS

class BaseParser(ABC):
    """Abstract base class for data parsers."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.records = []
        self.errors = []
        self.warnings = []
        self.detected_fields = set()
        self.metadata = {}

    @abstractmethod
    def parse(self) -> bool:
        """Parse the file and populate self.records."""
        pass

    def normalize_field_names(self, record: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {}

        for key, value in record.items():
            standard_name = None

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

    def extract_metadata(self, record: Dict[str, Any]) -> tuple:
        all_known_fields = set(REQUIRED_FIELDS + OPTIONAL_FIELDS)

        core_data = {k: v for k, v in record.items() if k in all_known_fields}
        metadata = {k: v for k, v in record.items() if k not in all_known_fields}

        return core_data, metadata

    def validate_all(self, qc_validator) -> None:
        for idx, record in enumerate(self.records):
            errors, warnings = qc_validator.validate_record(record, idx)
            self.errors.extend(errors)
            self.warnings.extend(warnings)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_records": len(self.records),
            "detected_fields": sorted(self.detected_fields),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }
