"""
Utility functions for data parsing and type conversion.

Provides safe type conversion functions with proper error handling
and type hints for use throughout the parsing pipeline.
"""

from typing import Optional, Union, Dict, Any, List
import json


def safe_int(value: Union[str, int, float, None]) -> Optional[int]:
    """
    Convert value to integer, returning None for invalid/empty values.
    
    Args:
        value: Value to convert (string, int, float, or None)
        
    Returns:
        Integer value or None if conversion fails or value is empty
        
    Examples:
        >>> safe_int(42)
        42
        >>> safe_int("123")
        123
        >>> safe_int("N/A")
        None
        >>> safe_int(None)
        None
    """
    try:
        if value in (None, '', 'NULL', 'null', 'None'):
            return None
        return int(value)
    except (ValueError, TypeError):
        return None


def safe_float(value: Union[str, int, float, None]) -> Optional[float]:
    """
    Convert value to float, returning None for invalid/empty values.
    
    Args:
        value: Value to convert (string, int, float, or None)
        
    Returns:
        Float value or None if conversion fails or value is empty
        
    Examples:
        >>> safe_float(3.14)
        3.14
        >>> safe_float("123.45")
        123.45
        >>> safe_float("N/A")
        None
        >>> safe_float(None)
        None
    """
    try:
        if value in (None, '', 'NULL', 'null', 'None'):
            return None
        return float(value)
    except (ValueError, TypeError):
        return None


def prepare_variant_data(
    record: Dict[str, Any],
    experiment_id: int,
    core_data: Dict[str, Any],
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Prepare variant data dictionary for database insertion.
    
    Args:
        record: Original parsed record
        experiment_id: Experiment ID for the variant
        core_data: Core fields extracted from record
        metadata: Additional metadata fields
        
    Returns:
        Dictionary ready for Variant model creation
    """
    return {
        'experiment_id': experiment_id,
        'variant_index': safe_int(core_data.get('variant_index')),
        'generation': safe_int(core_data.get('generation')),
        'parent_variant_index': safe_int(core_data.get('parent_variant_index')),
        'assembled_dna_sequence': core_data.get('assembled_dna_sequence'),
        'dna_yield': safe_float(core_data.get('dna_yield')),
        'protein_yield': safe_float(core_data.get('protein_yield')),
        'additional_metadata': json.dumps(metadata) if metadata else None,
    }


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split a list into chunks of specified size.
    
    Args:
        lst: List to split
        chunk_size: Maximum size of each chunk
        
    Returns:
        List of chunks
        
    Examples:
        >>> chunk_list([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
