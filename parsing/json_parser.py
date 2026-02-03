"""
JSON parser for experimental data.
Handles various JSON structures (array, nested objects).
"""

import json
from typing import Dict, List, Any
from parsing.base_parser import BaseParser

class JSONParser(BaseParser):
    """Parser for JSON files."""
    
    def _extract_records(self, data: Any) -> List[Dict]:
        """
        Extract record list from various JSON structures.
        
        Args:
            data: Parsed JSON data
            
        Returns:
            List of record dictionaries
        """
        # Case 1: Array of objects [{...}, {...}]
        if isinstance(data, list):
            return data
        
        # Case 2: Nested with 'records' key {"records": [...]}
        if isinstance(data, dict) and 'records' in data:
            return data['records']
        
        # Case 3: Nested with 'variants' key {"variants": [...]}
        if isinstance(data, dict) and 'variants' in data:
            return data['variants']
        
        # Case 4: Single object {...} - wrap in list
        if isinstance(data, dict):
            return [data]
        
        return []
    
    def parse(self) -> bool:
        """
        Parse JSON file.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract records from structure
            records = self._extract_records(data)
            
            if not records:
                self.errors.append("No records found in JSON file")
                return False
            
            # Process each record
            for idx, record in enumerate(records):
                # Normalize field names
                normalized = self.normalize_field_names(record)
                
                # Normalize DNA sequences
                for key, value in normalized.items():
                    if 'sequence' in key.lower() and isinstance(value, str):
                        normalized[key] = value.upper().replace(' ', '')
                
                # Store detected fields
                self.detected_fields.update(normalized.keys())
                
                # Add index for error reporting
                normalized['_row_number'] = idx + 1
                
                self.records.append(normalized)
            
            return True
            
        except FileNotFoundError:
            self.errors.append(f"File not found: {self.filepath}")
            return False
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON format: {str(e)}")
            return False
        except Exception as e:
            self.errors.append(f"Unexpected error parsing JSON: {str(e)}")
            return False