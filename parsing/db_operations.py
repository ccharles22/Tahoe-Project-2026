"""
Database operations for batch insert/update of variant records.

Adapted for normalized schema with experiments, generations, variants, and metrics tables.
"""

import logging
import json
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from parsing.models import Variant, Generation, Metric, Experiment
from parsing.utils import safe_int, safe_float

logger = logging.getLogger(__name__)

# Default user_id and wt_id for auto-creating experiments
# These should exist in the database (created during initial setup)
DEFAULT_USER_ID = 1
DEFAULT_WT_ID = 1


def get_or_create_experiment(session: Session, experiment_id: int) -> int:
    """
    Get an existing experiment or create a new one.
    
    If the experiment doesn't exist, it will be created with default
    user_id and wt_id values.
    """
    exp = session.query(Experiment).filter_by(experiment_id=experiment_id).first()
    if exp:
        return exp.experiment_id

    # Create new experiment with default user and wild type
    exp = Experiment(
        experiment_id=experiment_id,
        user_id=DEFAULT_USER_ID,
        wt_id=DEFAULT_WT_ID,
        name=f"Experiment {experiment_id}",
        description=f"Auto-created experiment {experiment_id}"
    )
    session.add(exp)
    try:
        session.flush()
        logger.info(f"Created experiment {exp.experiment_id}: {exp.name}")
    except IntegrityError:
        # Another transaction inserted it first; fetch instead
        session.rollback()
        existing = session.query(Experiment).filter_by(experiment_id=experiment_id).first()
        if not existing:
            raise
        exp = existing
    return exp.experiment_id


def get_or_create_generation(session: Session, experiment_id: int, generation_number: int) -> int:
    """Get or create a generation record."""
    gen = session.query(Generation).filter_by(
        experiment_id=experiment_id,
        generation_number=generation_number
    ).first()

    if gen:
        return gen.generation_id

    gen = Generation(
        experiment_id=experiment_id,
        generation_number=generation_number
    )
    session.add(gen)
    try:
        session.flush()
        logger.info(f"Created generation {generation_number} for experiment {experiment_id}")
    except IntegrityError:
        # Another transaction created it first; fetch existing instead of failing
        session.rollback()
        existing = session.query(Generation).filter_by(
            experiment_id=experiment_id,
            generation_number=generation_number
        ).first()
        if not existing:
            raise
        gen = existing

    return gen.generation_id


def insert_or_update_variant(
    session: Session,
    generation_id: int,
    plasmid_variant_index: str,
    assembled_dna_sequence: str,
    parent_variant_id: int = None
) -> int:
    """Insert or update a variant record."""
    variant = session.query(Variant).filter_by(
        generation_id=generation_id,
        plasmid_variant_index=plasmid_variant_index
    ).first()
    
    if variant:
        # Update existing
        variant.assembled_dna_sequence = assembled_dna_sequence
        if parent_variant_id:
            variant.parent_variant_id = parent_variant_id
        logger.debug(f"Updated variant {plasmid_variant_index}")
    else:
        # Insert new
        variant = Variant(
            generation_id=generation_id,
            plasmid_variant_index=plasmid_variant_index,
            assembled_dna_sequence=assembled_dna_sequence,
            parent_variant_id=parent_variant_id
        )
        session.add(variant)
        session.flush()
        logger.debug(f"Inserted variant {plasmid_variant_index}")
    
    return variant.variant_id


def insert_metric(
    session: Session,
    generation_id: int,
    variant_id: int,
    metric_name: str,
    value: float,
    unit: str = None
):
    """Insert or update a metric record."""
    if value is None:
        return
    
    # Check if metric already exists
    existing = session.query(Metric).filter_by(
        generation_id=generation_id,
        variant_id=variant_id,
        metric_name=metric_name,
        metric_type='raw'
    ).first()
    
    if existing:
        # Update existing metric
        existing.value = value
        if unit:
            existing.unit = unit
        logger.debug(f"Updated metric {metric_name} for variant {variant_id}")
    else:
        # Insert new metric
        metric = Metric(
            generation_id=generation_id,
            variant_id=variant_id,
            metric_name=metric_name,
            metric_type='raw',
            value=value,
            unit=unit
        )
        session.add(metric)


def batch_upsert_variants(
    session: Session,
    records: List[Dict[str, Any]],
    experiment_id: int,
    extract_metadata_func: callable
) -> Tuple[int, int]:
    """
    Batch insert/update variant records with normalized schema.
    
    Args:
        session: SQLAlchemy session
        records: List of parsed record dictionaries
        experiment_id: Experiment ID
        extract_metadata_func: Function to extract metadata
        
    Returns:
        Tuple of (inserted_count, updated_count)
    """
    if not records:
        return 0, 0
    
    inserted_count = 0
    updated_count = 0
    
    # Ensure experiment exists
    get_or_create_experiment(session, experiment_id)
    
    # Group records by generation
    records_by_generation = {}
    for record in records:
        generation_num = safe_int(record.get('generation', 0))
        if generation_num not in records_by_generation:
            records_by_generation[generation_num] = []
        records_by_generation[generation_num].append(record)
    
    # Process each generation
    for generation_num, gen_records in records_by_generation.items():
        generation_id = get_or_create_generation(session, experiment_id, generation_num)
        
        # Get existing variants for this generation
        plasmid_indices = [str(r.get('variant_index', r.get('Plasmid_Variant_Index', ''))) for r in gen_records]
        existing_variants = session.query(Variant).filter(
            Variant.generation_id == generation_id,
            Variant.plasmid_variant_index.in_(plasmid_indices)
        ).all()
        existing_map = {v.plasmid_variant_index: v for v in existing_variants}
        
        # Process each record
        for record in gen_records:
            plasmid_idx = str(record.get('variant_index', record.get('Plasmid_Variant_Index', '')))
            dna_seq = record.get('assembled_dna_sequence', record.get('Assembled_DNA_Sequence', ''))
            dna_yield_val = safe_float(record.get('dna_yield', record.get('DNA_Yield')))
            protein_yield_val = safe_float(record.get('protein_yield', record.get('Protein_Yield')))
            
            # Handle parent variant
            parent_variant_id = None
            parent_idx = record.get('parent_variant_index', record.get('Parent_Plasmid_Variant'))
            if parent_idx and parent_idx not in ['-1', -1, None, '']:
                # Look up parent variant_id (would need to query by plasmid_variant_index)
                parent_variant = session.query(Variant).filter_by(
                    plasmid_variant_index=str(parent_idx)
                ).first()
                if parent_variant:
                    parent_variant_id = parent_variant.variant_id
            
            # Insert or update variant
            if plasmid_idx in existing_map:
                variant = existing_map[plasmid_idx]
                variant.assembled_dna_sequence = dna_seq
                if parent_variant_id:
                    variant.parent_variant_id = parent_variant_id
                updated_count += 1
            else:
                variant = Variant(
                    generation_id=generation_id,
                    plasmid_variant_index=plasmid_idx,
                    assembled_dna_sequence=dna_seq,
                    parent_variant_id=parent_variant_id
                )
                session.add(variant)
                session.flush()  # Get variant_id
                inserted_count += 1
            
            # Insert metrics
            variant_id = variant.variant_id
            if dna_yield_val is not None:
                insert_metric(session, generation_id, variant_id, 'dna_yield', dna_yield_val, 'ng/µL')
            if protein_yield_val is not None:
                insert_metric(session, generation_id, variant_id, 'protein_yield', protein_yield_val, 'mg/mL')
    
    logger.info(f"Batch complete: {inserted_count} inserted, {updated_count} updated for experiment {experiment_id}")
    return inserted_count, updated_count


def batch_insert_variants(
    session: Session,
    records: List[Dict[str, Any]],
    experiment_id: int,
    extract_metadata_func: callable
) -> int:
    """Batch insert variant records (delegates to upsert)."""
    inserted, _ = batch_upsert_variants(session, records, experiment_id, extract_metadata_func)
    return inserted
