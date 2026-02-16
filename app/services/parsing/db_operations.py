"""
Database operations for batch insert/update of variant records.

Provides optimized batch operations with all-or-nothing transaction semantics.
Uses bulk operations where possible for improved performance with large datasets.
"""

import logging
from typing import List, Dict, Any, Tuple, Set
from sqlalchemy.orm import Session

from app.models import Variant
from app.services.parsing.utils import safe_int, safe_float, prepare_variant_data

logger = logging.getLogger(__name__)


def get_existing_variant_indices(
    session: Session,
    experiment_id: int
) -> Set[int]:
    """
    Fetch all existing variant indices for an experiment.

    This is done once before batch processing to avoid N+1 queries.

    Args:
        session: SQLAlchemy session
        experiment_id: Experiment ID to query

    Returns:
        Set of existing variant indices
    """
    try:
        rows = session.query(Variant.variant_index).filter_by(
            experiment_id=experiment_id
        ).all()
        return {row[0] for row in rows if row[0] is not None}
    except Exception as exc:
        logger.warning("Error fetching existing variant indices: %s", exc)
        return set()


def get_existing_variants_map(
    session: Session,
    experiment_id: int,
    variant_indices: List[int]
) -> Dict[int, Variant]:
    """
    Fetch existing Variant objects for given indices.

    Args:
        session: SQLAlchemy session
        experiment_id: Experiment ID
        variant_indices: List of variant indices to fetch

    Returns:
        Dictionary mapping variant_index to Variant object
    """
    if not variant_indices:
        return {}

    try:
        variants = session.query(Variant).filter(
            Variant.experiment_id == experiment_id,
            Variant.variant_index.in_(variant_indices)
        ).all()
        return {v.variant_index: v for v in variants}
    except Exception as exc:
        logger.warning("Error fetching existing variants: %s", exc)
        return {}


def batch_upsert_variants(
    session: Session,
    records: List[Dict[str, Any]],
    experiment_id: int,
    extract_metadata_func: callable
) -> Tuple[int, int]:
    """
    Batch insert/update variant records with all-or-nothing semantics.

    This function optimizes database operations by:
    1. Fetching all existing variant indices in one query
    2. Separating records into insert vs update batches
    3. Using bulk operations where possible
    4. Committing all changes in a single transaction

    If any error occurs, the entire batch is rolled back.

    Args:
        session: SQLAlchemy session (caller manages commit/rollback)
        records: List of parsed record dictionaries
        experiment_id: Experiment ID for all records
        extract_metadata_func: Function to extract core_data and metadata from record

    Returns:
        Tuple of (inserted_count, updated_count)

    Raises:
        Exception: Re-raises any database error after logging

    Example:
        >>> session = db.session
        >>> try:
        ...     inserted, updated = batch_upsert_variants(
        ...         session, records, 1, parser.extract_metadata
        ...     )
        ...     session.commit()
        ... except Exception:
        ...     session.rollback()
        ...     raise
    """
    if not records:
        return 0, 0

    inserted_count = 0
    updated_count = 0

    # Prepare all variant data first
    prepared_records = []
    for record in records:
        core_data, metadata = extract_metadata_func(record)
        variant_data = prepare_variant_data(record, experiment_id, core_data, metadata)
        prepared_records.append(variant_data)

    # Get indices we need to check
    indices_to_check = [
        r['variant_index'] for r in prepared_records
        if r['variant_index'] is not None
    ]

    # Fetch existing variants in one query
    existing_variants = get_existing_variants_map(
        session, experiment_id, indices_to_check
    )

    # Separate into inserts and updates
    to_insert = []

    for variant_data in prepared_records:
        v_index = variant_data['variant_index']

        if v_index in existing_variants:
            # Update existing record
            existing = existing_variants[v_index]
            existing.generation = variant_data['generation']
            existing.parent_variant_index = variant_data['parent_variant_index']
            existing.assembled_dna_sequence = variant_data['assembled_dna_sequence']
            existing.dna_yield = variant_data['dna_yield']
            existing.protein_yield = variant_data['protein_yield']
            existing.additional_metadata = variant_data['additional_metadata']
            updated_count += 1
        else:
            # New record to insert
            to_insert.append(variant_data)

    # Bulk insert new records
    if to_insert:
        # Use bulk_insert_mappings for better performance
        session.bulk_insert_mappings(Variant, to_insert)
        inserted_count = len(to_insert)

    logger.info(
        "Batch upsert complete: %s inserted, %s updated for experiment %s",
        inserted_count,
        updated_count,
        experiment_id,
    )

    return inserted_count, updated_count


def batch_insert_variants(
    session: Session,
    records: List[Dict[str, Any]],
    experiment_id: int,
    extract_metadata_func: callable
) -> int:
    """
    Batch insert variant records (no update, fails on duplicates).

    Use this when you know all records are new. More efficient than
    upsert as it skips the existence check.

    Args:
        session: SQLAlchemy session
        records: List of parsed record dictionaries
        experiment_id: Experiment ID for all records
        extract_metadata_func: Function to extract core_data and metadata

    Returns:
        Number of records inserted

    Raises:
        IntegrityError: If duplicate variant_index exists
    """
    if not records:
        return 0

    to_insert = []
    for record in records:
        core_data, metadata = extract_metadata_func(record)
        variant_data = prepare_variant_data(record, experiment_id, core_data, metadata)
        to_insert.append(variant_data)

    session.bulk_insert_mappings(Variant, to_insert)

    logger.info("Batch insert complete: %s records for experiment %s", len(to_insert), experiment_id)

    return len(to_insert)
