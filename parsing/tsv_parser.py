"""
TSV/CSV parser for experimental data.
Handles tab-delimited and comma-delimited files.
"""

import csv
from typing import Dict, Any
from parsing.base_parser import BaseParser


class TSVParser(BaseParser):
    """Parser for TSV and CSV files."""

    def __init__(self, filepath: str):
        super().__init__(filepath)
        self.delimiter = None

    def _detect_delimiter(self, first_line: str) -> str:
        tab_count = first_line.count("\t")
        comma_count = first_line.count(",")
        return "\t" if tab_count > comma_count else ","

    def _clean_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        cleaned = {}

        for key, value in row.items():
            clean_key = key.strip() if key else key
            clean_value = value.strip() if isinstance(value, str) else value

            # Normalize DNA sequences
            if clean_key and "sequence" in clean_key.lower():
                if isinstance(clean_value, str):
                    clean_value = clean_value.upper().replace(" ", "")

            # Numeric coercion
            if clean_key in {
                "DNA_Quantification_fg",
                "Protein_Quantification_pg",
            }:
                try:
                    clean_value = float(clean_value)
                except (TypeError, ValueError):
                    pass

            if clean_key in {
                "Plasmid_Variant_Index",
                "Parent_Plasmid_Variant",
                "Directed_Evolution_Generation",
            }:
                try:
                    clean_value = int(clean_value)
                except (TypeError, ValueError):
                    pass

            cleaned[clean_key] = clean_value

        return cleaned

    # ✅ REQUIRED concrete implementation
    def parse(self) -> bool:
        """Parse TSV/CSV file."""
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                first_line = f.readline()
                self.delimiter = self._detect_delimiter(first_line)
                f.seek(0)

                reader = csv.DictReader(f, delimiter=self.delimiter)

                for row_num, row in enumerate(reader, start=2):
                    if not any(row.values()):
                        continue

                    try:
                        cleaned = self._clean_row(row)
                        normalized = self.normalize_field_names(cleaned)

                        self.detected_fields.update(normalized.keys())
                        normalized["_row_number"] = row_num
                        self.records.append(normalized)

                    except Exception as row_error:
                        self.errors.append(f"Row {row_num}: {row_error}")

            return True

        except FileNotFoundError:
            self.errors.append(f"File not found: {self.filepath}")
            return False
        except UnicodeDecodeError:
            self.errors.append(
                "File encoding error. Please ensure file is UTF-8 encoded."
            )
            return False
        except Exception as e:
            self.errors.append(f"Unexpected error parsing TSV: {e}")
            return False

