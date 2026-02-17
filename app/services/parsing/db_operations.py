"""
Database operations for batch insert/update of variant records.

Adapted for the normalised Postgres schema:
  experiments -> generations -> variants -> metrics

Records from parsed files are grouped by generation_number, inserted into
the generations table, then variants + metric rows are created.
"""

import logging
from typing import List, Dict, Any, Tuple, Set, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import Generation, Variant, Metric
from app.services.parsing.utils import safe_int, safe_float

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def get_or_create_generation(
    session: Session,
    experiment_id: int,
    generation_number: int,
) -> Generation:
    """Return existing Generation or create a new one (idempotent)."""
    gen = session.query(Generation).filter_by(
        experiment_id=experiment_id,
        generation_number=generation_number,
    ).first()
    if gen:
        return gen

    gen = Generation(
        experiment_id=experiment_id,
        generation_number=generation_number,
    )
    session.add(gen)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        gen = session.query(Generation).filter_by(
            experiment_id=experiment_id,
            generation_number=generation_number,
        ).first()
    return gen


def _create_metrics_for_variant(
    session: Session,
    generation_id: int,
    variant_id: int,
    dna_yield: Optional[float],
    protein_yield: Optional[float],
) -> int:
    """Insert metric rows for a variant. Returns count of metrics created."""
    count = 0
    if dna_yield is not None:
        session.add(Metric(
            generation_id=generation_id,
            variant_id=variant_id,
            metric_name="dna_yield",
            metric_type="raw",
            value=dna_yield,
            unit="ng/uL",
        ))
        count += 1
    if protein_yield is not None:
        session.add(Metric(
            generation_id=generation_id,
            variant_id=variant_id,
            metric_name="protein_yield",
            metric_type="raw",
            value=protein_yield,
            unit="mg/L",
        ))
        count += 1
    return count


# ---------------------------------------------------------------------------
# public API -- called from parsing routes
# ---------------------------------------------------------------------------

def batch_upsert_variants(
    session: Session,
    records: List[Dict[str, Any]],
    experiment_id: int,
    extract_metadata_func: callable,
) -> Tuple[int, int]:
    """
    Parse records and persist into generations -> variants -> metrics.

    Uses no_autoflush + periodic batch flushes for connection stability
    on remote Postgres over Tailscale/VPN.

    Args:
        session: SQLAlchemy session (caller commits/rollbacks)
        records: List of parsed record dicts
        experiment_id: Target experiment
        extract_metadata_func: Parser helper that splits a record into
            (core_data, extra_metadata)

    Returns:
        (inserted_count, updated_count)
    """
    if not records:
        return 0, 0

    inserted_count = 0
    updated_count = 0
    BATCH_SIZE = 50

    # Pre-create all generations first
    gen_cache: Dict[int, Generation] = {}
    gen_nums_needed: Set[int] = set()
    for record in records:
        core_data, _ = extract_metadata_func(record)
        gen_nums_needed.add(safe_int(core_data.get("generation")) or 0)

    for gn in gen_nums_needed:
        gen_cache[gn] = get_or_create_generation(session, experiment_id, gn)
    session.flush()

    # Process variants + metrics inside no_autoflush to avoid
    # mid-loop flushes that can fail on flaky connections.
    with session.no_autoflush:
        pending_new: list = []

        for i, record in enumerate(records):
            core_data, metadata = extract_metadata_func(record)

            gen_num = safe_int(core_data.get("generation")) or 0
            variant_index = str(safe_int(core_data.get("variant_index")) or "0")
            dna_seq = core_data.get("assembled_dna_sequence")
            dna_yield = safe_float(core_data.get("dna_yield"))
            protein_yield = safe_float(core_data.get("protein_yield"))

            gen = gen_cache[gen_num]

            existing = session.query(Variant).filter_by(
                generation_id=gen.generation_id,
                plasmid_variant_index=variant_index,
            ).first()

            if existing:
                existing.assembled_dna_sequence = dna_seq
                existing.extra_metadata = metadata or None
                session.query(Metric).filter_by(variant_id=existing.variant_id).delete()
                _create_metrics_for_variant(
                    session, gen.generation_id, existing.variant_id,
                    dna_yield, protein_yield,
                )
                updated_count += 1
            else:
                v = Variant(
                    generation_id=gen.generation_id,
                    plasmid_variant_index=variant_index,
                    assembled_dna_sequence=dna_seq,
                    extra_metadata=metadata or None,
                )
                session.add(v)
                pending_new.append((v, gen.generation_id, dna_yield, protein_yield))
                inserted_count += 1

            if (i + 1) % BATCH_SIZE == 0:
                session.flush()
                for v_obj, gid, dy, py_ in pending_new:
                    _create_metrics_for_variant(session, gid, v_obj.variant_id, dy, py_)
                pending_new.clear()
                session.flush()

        # Final flush for remaining records
        session.flush()
        for v_obj, gid, dy, py_ in pending_new:
            _create_metrics_for_variant(session, gid, v_obj.variant_id, dy, py_)
        pending_new.clear()
        session.flush()

    logger.info(
        f"Batch upsert complete: {inserted_count} inserted, {updated_count} updated "
        f"for experiment {experiment_id}"
    )
    return inserted_count, updated_count


def batch_insert_variants(
    session: Session,
    records: List[Dict[str, Any]],
    experiment_id: int,
    extract_metadata_func: callable,
) -> int:
    """Insert-only variant of batch_upsert_variants."""
    inserted, _ = batch_upsert_variants(
        session, records, experiment_id, extract_metadata_func,
    )
    return inserted
