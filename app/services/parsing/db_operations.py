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
from sqlalchemy import text

from app.models import Experiment, Generation, Metric, Variant, WildtypeControl
from app.services.parsing.utils import safe_bool, safe_float, safe_int

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


def get_or_create_wt_control(
    session: Session,
    generation_id: int,
    wt_id: int,
) -> WildtypeControl:
    """Return existing WT control row or create one for the generation."""
    wt_control = session.query(WildtypeControl).filter_by(
        generation_id=generation_id,
        wt_id=wt_id,
    ).first()
    if wt_control:
        return wt_control

    wt_control = WildtypeControl(generation_id=generation_id, wt_id=wt_id)
    session.add(wt_control)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        wt_control = session.query(WildtypeControl).filter_by(
            generation_id=generation_id,
            wt_id=wt_id,
        ).first()
    return wt_control


def _create_raw_metrics(
    session: Session,
    generation_id: int,
    *,
    variant_id: Optional[int] = None,
    wt_control_id: Optional[int] = None,
    dna_yield: Optional[float],
    protein_yield: Optional[float],
) -> int:
    """
    Insert raw metric rows for either a variant or a WT control.

    The imported example files express raw assay values in femtograms and
    picograms, so the parser must preserve both the semantic metric names and
    the source units.
    """
    count = 0
    if dna_yield is not None:
        session.add(Metric(
            generation_id=generation_id,
            variant_id=variant_id,
            wt_control_id=wt_control_id,
            metric_name="dna_yield_raw",
            metric_type="raw",
            value=dna_yield,
            unit="fg",
        ))
        count += 1
    if protein_yield is not None:
        session.add(Metric(
            generation_id=generation_id,
            variant_id=variant_id,
            wt_control_id=wt_control_id,
            metric_name="protein_yield_raw",
            metric_type="raw",
            value=protein_yield,
            unit="pg",
        ))
        count += 1
    return count


def _clear_variant_outputs(session: Session, variant_id: int) -> None:
    """
    Remove stored sequence-analysis outputs for a variant.

    Re-uploaded parsing data replaces the source DNA sequence and raw assay
    values, so every downstream artefact derived from the previous upload must
    be cleared before the experiment is processed again.
    """
    session.execute(
        text("DELETE FROM public.variant_sequence_analysis WHERE variant_id = :vid"),
        {"vid": variant_id},
    )
    session.execute(
        text("DELETE FROM public.mutations WHERE variant_id = :vid"),
        {"vid": variant_id},
    )
    session.query(Metric).filter_by(variant_id=variant_id).delete()


def _merge_variant_extra_metadata(
    existing_metadata: Optional[Dict[str, Any]],
    new_metadata: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Merge parser metadata onto existing variant metadata while dropping
    stale sequence-analysis payloads that are no longer valid after re-upload.
    """
    merged: Dict[str, Any] = {}

    if isinstance(existing_metadata, dict):
        merged.update(existing_metadata)
        merged.pop("sequence_analysis", None)

    if isinstance(new_metadata, dict):
        merged.update(new_metadata)

    return merged or None


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

    experiment = session.get(Experiment, experiment_id)
    if not experiment:
        raise ValueError(f"Experiment {experiment_id} does not exist.")

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
        pending_parent_links: list = []
        wt_control_cache: Dict[int, WildtypeControl] = {}
        cleared_wt_generations: Set[int] = set()
        wt_control_values: Dict[int, Dict[str, list[float]]] = {}

        for i, record in enumerate(records):
            core_data, metadata = extract_metadata_func(record)

            gen_num = safe_int(core_data.get("generation")) or 0
            variant_index = str(safe_int(core_data.get("variant_index")) or "0")
            parent_variant_index = safe_int(core_data.get("parent_variant_index"))
            dna_seq = core_data.get("assembled_dna_sequence")
            dna_yield = safe_float(core_data.get("dna_yield"))
            protein_yield = safe_float(core_data.get("protein_yield"))
            is_control = bool(safe_bool(core_data.get("control")))

            gen = gen_cache[gen_num]

            if is_control:
                wt_control = wt_control_cache.get(gen_num)
                if wt_control is None:
                    wt_control = get_or_create_wt_control(
                        session,
                        gen.generation_id,
                        experiment.wt_id,
                    )
                    wt_control_cache[gen_num] = wt_control

                if gen_num not in cleared_wt_generations:
                    had_existing_wt_metrics = (
                        session.query(Metric)
                        .filter_by(wt_control_id=wt_control.wt_control_id)
                        .first()
                        is not None
                    )
                    if had_existing_wt_metrics:
                        updated_count += 1
                    else:
                        inserted_count += 1

                    session.query(Metric).filter_by(
                        wt_control_id=wt_control.wt_control_id
                    ).delete()
                    cleared_wt_generations.add(gen_num)

                bucket = wt_control_values.setdefault(
                    gen_num,
                    {"dna": [], "protein": []},
                )
                if dna_yield is not None:
                    bucket["dna"].append(dna_yield)
                if protein_yield is not None:
                    bucket["protein"].append(protein_yield)

                stale_variant = session.query(Variant).filter_by(
                    generation_id=gen.generation_id,
                    plasmid_variant_index=variant_index,
                ).first()
                if stale_variant:
                    _clear_variant_outputs(session, stale_variant.variant_id)
                    session.delete(stale_variant)
                    session.flush()

                if (i + 1) % BATCH_SIZE == 0:
                    session.flush()
                continue

            existing = session.query(Variant).filter_by(
                generation_id=gen.generation_id,
                plasmid_variant_index=variant_index,
            ).first()

            if existing:
                existing.assembled_dna_sequence = dna_seq
                existing.extra_metadata = _merge_variant_extra_metadata(existing.extra_metadata, metadata)
                existing.protein_sequence = None
                _clear_variant_outputs(session, existing.variant_id)
                _create_raw_metrics(
                    session,
                    gen.generation_id,
                    variant_id=existing.variant_id,
                    dna_yield=dna_yield,
                    protein_yield=protein_yield,
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
                if (
                    parent_variant_index is not None
                    and parent_variant_index >= 0
                    and gen_num > 0
                ):
                    pending_parent_links.append((v, gen_num, parent_variant_index))
                inserted_count += 1

            if (i + 1) % BATCH_SIZE == 0:
                session.flush()
                for v_obj, gid, dy, py_ in pending_new:
                    _create_raw_metrics(
                        session,
                        gid,
                        variant_id=v_obj.variant_id,
                        dna_yield=dy,
                        protein_yield=py_,
                    )
                pending_new.clear()
                session.flush()

        # Final flush for remaining records
        session.flush()
        for v_obj, gid, dy, py_ in pending_new:
            _create_raw_metrics(
                session,
                gid,
                variant_id=v_obj.variant_id,
                dna_yield=dy,
                protein_yield=py_,
            )
        pending_new.clear()
        session.flush()

        for gen_num, values in wt_control_values.items():
            wt_control = wt_control_cache[gen_num]
            dna_values = values["dna"]
            protein_values = values["protein"]
            avg_dna = (
                sum(dna_values) / len(dna_values)
                if dna_values
                else None
            )
            avg_protein = (
                sum(protein_values) / len(protein_values)
                if protein_values
                else None
            )
            _create_raw_metrics(
                session,
                gen_cache[gen_num].generation_id,
                wt_control_id=wt_control.wt_control_id,
                dna_yield=avg_dna,
                protein_yield=avg_protein,
            )
        session.flush()

        variant_rows = (
            session.query(
                Variant.variant_id,
                Generation.generation_number,
                Variant.plasmid_variant_index,
            )
            .join(Generation, Generation.generation_id == Variant.generation_id)
            .filter(Generation.experiment_id == experiment_id)
            .all()
        )
        variant_lookup = {
            (int(generation_number), str(plasmid_variant_index)): int(variant_id)
            for variant_id, generation_number, plasmid_variant_index in variant_rows
        }

        for variant_obj, gen_num, parent_index in pending_parent_links:
            parent_key = (gen_num - 1, str(parent_index))
            variant_obj.parent_variant_id = variant_lookup.get(parent_key)

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
