"""
Database repository layer for the sequence processing pipeline.

Provides all SQL persistence operations required by the sequence analysis
workflow, including:
    - WT reference and variant retrieval
    - Mutation storage (synonymous / nonsynonymous / indel classification)
    - Derived metric persistence (mutation counts)
    - Experiment status tracking and run metadata
    - WT mapping cache (avoids 6-frame recomputation)
    - UniProt staging for WT protein accession data
    - Atomic end-to-end variant analysis persistence

Dependencies:
    - SQLAlchemy (create_engine, text, Connection, Engine)
    - app.config.settings for DATABASE_URL and pipeline configuration
"""
from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple, Union

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.config import settings

if TYPE_CHECKING:
    from app.services.sequence.sequence_service import (
        WTMapping,
        VariantSeqResult,
        MutationRecord,
        MutationCounts,
    )

logger = logging.getLogger(__name__)

# Mutation types that can be stored in the mutations table.
# These types always have valid position, original, and mutated values
# that satisfy the schema's NOT NULL and CHECK constraints.
# Other types (FRAMESHIFT, INSERTION, DELETION) are persisted only in
# the variant's extra_metadata JSONB column.
_INSERTABLE_MUTATION_TYPES = {"SYNONYMOUS", "NONSYNONYMOUS", "NONSENSE", "AMBIGUOUS"}


# =============================================================================
# Engine
# =============================================================================

def get_engine() -> Engine:
    """
    Creates and returns a SQLAlchemy engine using the application DATABASE_URL.

    The engine is configured with:
        - pool_pre_ping: validates connections before use (handles stale connections)
        - future: enables SQLAlchemy 2.0 style usage

    Returns:
        Engine: Configured SQLAlchemy engine instance.
    """
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)


# =============================================================================
# WT Reference
# =============================================================================

def get_wt_reference(engine: Engine, experiment_id: int) -> Tuple[str, str]:
    """
    Retrieves the wild-type protein and plasmid sequences for an experiment.

    Joins the experiments table with wild_type_proteins to fetch the WT
    amino acid sequence and original plasmid DNA which are both required as
    inputs to the 6-frame WT gene mapping step.

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.

    Returns:
        Tuple of (wt_protein_aa, wt_plasmid_dna).

    Raises:
        ValueError: If no WT reference is linked to the experiment.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT w.amino_acid_sequence, w.plasmid_sequence
                FROM public.experiments e
                JOIN public.wild_type_proteins w
                  ON w.wt_id = e.wt_id
                WHERE e.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()

    if not row:
        raise ValueError(f"No WT reference found for experiment_id={experiment_id}")

    logger.debug("Loaded WT reference for experiment %s", experiment_id)
    return str(row[0]), str(row[1])


# =============================================================================
# Experiment helpers
# =============================================================================

def get_experiment_user_and_wt(
    engine: Engine,
    experiment_id: int,
) -> Tuple[int, int]:
    """
    Returns the owning user_id and wt_id for an experiment.

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.

    Returns:
        Tuple of (user_id, wt_id).

    Raises:
        ValueError: If the experiment does not exist.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_id, wt_id
                FROM public.experiments
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()

    if not row:
        raise ValueError(f"Experiment not found: {experiment_id}")

    return int(row[0]), int(row[1])


def update_experiment_status(
    engine: Engine,
    experiment_id: int,
    status: str,
) -> None:
    """
    Records the pipeline analysis status for an experiment.

    Status values used by the orchestrator:
        ANALYSIS_RUNNING, ANALYSED, ANALYSED_WITH_ERRORS, FAILED

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.
        status: New status string to record.
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE public.experiments
                SET analysis_status = :status
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id, "status": status},
        )
    logger.info("Experiment %s status → %s", experiment_id, status)


# =============================================================================
# Variants
# =============================================================================

def list_variants_by_experiment(
    engine: Engine,
    experiment_id: int,
) -> List[Tuple[int, str]]:
    """
    Obtains all variants for an experiment, ordered by generation then variant_id.
    Intentionally skips rows where assembled_dna_sequence is NULL (incomplete uploads).

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.

    Returns:
        List of (variant_id, assembled_dna_sequence) tuples.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT v.variant_id, v.assembled_dna_sequence
                FROM public.variants v
                JOIN public.generations g
                  ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                ORDER BY g.generation_number, v.variant_id
            """),
            {"eid": experiment_id},
        ).fetchall()

    results = [(int(r[0]), str(r[1])) for r in rows if r[1] is not None]
    logger.debug("Loaded %d variants for experiment %s", len(results), experiment_id)
    return results


def list_processed_variant_ids(
    engine: Engine,
    experiment_id: int,
) -> set:
    """
    Returns the set of variant_ids that already have a protein_sequence
    recorded, indicating they were previously processed.

    Used by the orchestrator to skip re-processing unchanged variants.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT v.variant_id
                FROM public.variants v
                JOIN public.generations g
                  ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                  AND v.protein_sequence IS NOT NULL
            """),
            {"eid": experiment_id},
        ).fetchall()
    return {int(r[0]) for r in rows}


def get_variant_generation_id(engine: Engine, variant_id: int) -> int:
    """
    Looks up the generation_id that owns a variant.

    Args:
        engine: SQLAlchemy engine instance.
        variant_id: Primary key of the variant.

    Returns:
        The generation_id (int).

    Raises:
        ValueError: If the variant does not exist.
    """
    with engine.connect() as conn:
        gid = conn.execute(
            text("SELECT generation_id FROM public.variants WHERE variant_id = :vid"),
            {"vid": variant_id},
        ).scalar_one_or_none()

    if gid is None:
        raise ValueError(f"Variant not found: {variant_id}")

    return int(gid)


# =============================================================================
# WT Mapping Cache
# =============================================================================

def load_wt_mapping(
    engine: Engine,
    experiment_id: int,
    user_id: int,
) -> Optional["WTMapping"]:
    """
    Loads a previously cached WT gene mapping from the database.

    The mapping is stored as a JSON string in experiment_metadata under the key
    'wt_mapping_json'. This then returns None on a cache miss
    so the caller can compute and cache it via upsert_wt_mapping.

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.
        user_id: User who owns the mapping (stored in the JSON for
                 traceability, but the lookup key is experiment_id only).

    Returns:
        Reconstructed WTMapping dataclass, or None if not cached.
    """
    from app.services.sequence.sequence_service import WTMapping  # deferred to avoid circular import

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT field_value
                FROM public.experiment_metadata
                WHERE experiment_id = :eid
                  AND field_name = 'wt_mapping_json'
            """),
            {"eid": experiment_id},
        ).fetchone()

    if not row or not row[0]:
        logger.debug("No cached WT mapping for experiment %s", experiment_id)
        return None

    data: Dict[str, Any] = json.loads(row[0])

    # The stored JSON may contain a 'user_id' key for provenance — strip it
    # before constructing the dataclass so it doesn't cause a TypeError.
    data.pop("user_id", None)

    logger.debug("Loaded cached WT mapping for experiment %s", experiment_id)
    return WTMapping(**data)


def upsert_wt_mapping(
    engine: Engine,
    experiment_id: int,
    user_id: int,
    wt_mapping: "WTMapping",
) -> None:
    """
    Caches a WT gene mapping result in the database.

    Serialises the WTMapping dataclass to a JSON string and stores it in
    experiment_metadata under 'wt_mapping_json'.
    Uses an upsert so re-running the pipeline safely overwrites stale data.

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.
        user_id: User who owns the mapping (stored inside the JSON).
        wt_mapping: WTMapping dataclass to persist.
    """
    mapping_dict = dataclasses.asdict(wt_mapping)
    mapping_dict["user_id"] = user_id  # embed provenance

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO public.experiment_metadata
                  (experiment_id, field_name, field_value)
                VALUES
                  (:eid, 'wt_mapping_json', :val)
                ON CONFLICT (experiment_id, field_name)
                DO UPDATE SET field_value = EXCLUDED.field_value
            """),
            {
                "eid": experiment_id,
                "val": json.dumps(mapping_dict),
            },
        )
    logger.info("Cached WT mapping for experiment %s", experiment_id)


# =============================================================================
# UniProt Staging
# =============================================================================

def upsert_uniprot_staging(
    engine: Engine,
    experiment_id: int,
    user_id: int,
    accession: str,
    protein_sequence: str,
) -> None:
    """
    Stages a UniProt protein sequence for an experiment.

    Stores the accession, user_id, and retrieved protein as a JSON string
    in experiment_metadata under 'uniprot_staging', so
    it can be used for WT mapping without re-fetching from UniProt.

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Primary key of the experiment.
        user_id: User who triggered the staging.
        accession: UniProt accession identifier (e.g. "P00582").
        protein_sequence: Full amino acid sequence from UniProt.
    """
    payload = json.dumps({
        "user_id": user_id,
        "accession": accession,
        "protein_sequence": protein_sequence,
    })

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO public.experiment_metadata
                  (experiment_id, field_name, field_value)
                VALUES
                  (:eid, 'uniprot_staging', :val)
                ON CONFLICT (experiment_id, field_name)
                DO UPDATE SET field_value = EXCLUDED.field_value
            """),
            {
                "eid": experiment_id,
                "val": payload,
            },
        )
    logger.info(
        "Staged UniProt %s for experiment %s (len=%d)",
        accession, experiment_id, len(protein_sequence),
    )


# =============================================================================
# Mutations (public.mutations)
# =============================================================================

def _write_mutations(
    conn: Connection,
    variant_id: int,
    mutations: Iterable["MutationRecord"],
    mutation_type: str = "protein",
    vsa_id: Optional[int] = None,
) -> int:
    """
    Writes mutations on an existing connection (no transaction management).

    Performs a scoped delete-then-insert for idempotent replacement of all
    mutation records of the given mutation_type for one variant.

    Schema constraints on public.mutations:
        - position integer NOT NULL, CHECK position > 0
        - original char(1) NOT NULL, CHECK valid amino acid / base
        - mutated  char(1) NOT NULL, CHECK valid amino acid / base

    Mutations of types that cannot satisfy these constraints (FRAMESHIFT,
    INSERTION, DELETION) are skipped here.  They are preserved in the
    VSA row's qc_flags JSONB.

    Args:
        conn: Active SQLAlchemy connection (caller manages transaction).
        variant_id: Target variant primary key.
        mutations: Iterable of MutationRecord dataclass instances.
        mutation_type: Scope of mutations — ``'protein'`` or ``'dna'``.
        vsa_id: Optional FK to variant_sequence_analysis for traceability.

    Returns:
        Number of mutations written (excludes skipped types).
    """
    muts = list(mutations)

    # Remove existing records for this scope before re-inserting
    conn.execute(
        text("""
            DELETE FROM public.mutations
            WHERE variant_id = :vid
              AND mutation_type = :mt
        """),
        {"vid": variant_id, "mt": mutation_type},
    )

    # Pre-filter and build parameter dicts for batch insert
    batch_params = []
    skipped = 0

    for m in muts:
        if m.mutation_type not in _INSERTABLE_MUTATION_TYPES:
            skipped += 1
            continue

        if m.aa_position_1based is None or m.wt_aa is None or m.var_aa is None:
            skipped += 1
            logger.warning(
                "Skipping %s mutation for variant %s: missing position/original/mutated",
                m.mutation_type, variant_id,
            )
            continue

        is_syn: Optional[bool] = None
        if m.mutation_type == "SYNONYMOUS":
            is_syn = True
        elif m.mutation_type in {"NONSYNONYMOUS", "NONSENSE"}:
            is_syn = False

        batch_params.append({
            "vid": variant_id,
            "mt": mutation_type,
            "pos": int(m.aa_position_1based),
            "orig": str(m.wt_aa),
            "mut": str(m.var_aa),
            "syn": is_syn,
            "ann": m.notes,
            "vsa": vsa_id,
        })

    written = len(batch_params)

    if batch_params:
        conn.execute(
            text("""
                INSERT INTO public.mutations
                  (variant_id, mutation_type, position,
                   original, mutated, is_synonymous, annotation, vsa_id)
                VALUES
                  (:vid, :mt, :pos,
                   :orig, :mut, :syn, :ann, :vsa)
                ON CONFLICT (variant_id, mutation_type, position, original, mutated)
                DO UPDATE SET
                  is_synonymous = EXCLUDED.is_synonymous,
                  annotation    = EXCLUDED.annotation,
                  vsa_id        = EXCLUDED.vsa_id
            """),
            batch_params,
        )

    if skipped:
        logger.info(
            "Variant %s: wrote %d mutations, skipped %d (FRAMESHIFT/INSERTION/DELETION "
            "stored in VSA qc_flags only)",
            variant_id, written, skipped,
        )
    else:
        logger.debug(
            "Wrote %d %s mutations for variant %s", written, mutation_type, variant_id,
        )

    return written


def replace_variant_mutations(
    engine: Engine,
    variant_id: int,
    mutations: Iterable["MutationRecord"],
    mutation_type: str = "protein",
    *,
    conn: Optional[Connection] = None,
) -> None:
    """
    Replaces all mutations of a given type for a variant (idempotent upsert).
    Deletes existing records collected by variant_id and mutation_type and
    inserts fresh rows.

    Args:
        engine: SQLAlchemy engine instance.
        variant_id: Target variant primary key.
        mutations: MutationRecord instances to persist.
        mutation_type: ``'protein'`` (default) or ``'dna'``.
        conn: Optional existing connection for shared transactions.
    """
    if conn is not None:
        _write_mutations(conn, variant_id, mutations, mutation_type)
    else:
        with engine.begin() as txn_conn:
            _write_mutations(txn_conn, variant_id, mutations, mutation_type)


# =============================================================================
# Metrics (public.metrics)
# =============================================================================

def _write_metrics(
    conn: Connection,
    variant_id: int,
    generation_id: int,
    counts: "MutationCounts",
) -> None:
    """
    Persists three metric rows per variant:
        - mutation_synonymous_count
        - mutation_nonsynonymous_count
        - mutation_total_count

    Args:
        conn: Active SQLAlchemy connection (caller manages transaction).
        variant_id: Target variant primary key.
        generation_id: Generation that owns this variant (for FK).
        counts: MutationCounts dataclass with aggregated statistics.
    """
    metrics = {
        "mutation_synonymous_count": counts.synonymous,
        "mutation_nonsynonymous_count": counts.nonsynonymous,
        "mutation_total_count": counts.total,
    }

    conn.execute(
        text("""
            INSERT INTO public.metrics
              (generation_id, variant_id,
               metric_name, metric_type,
               value, unit)
            VALUES
              (:gid, :vid,
               :name, 'derived',
               :val, 'count')
            ON CONFLICT (generation_id, variant_id, metric_name, metric_type)
              WHERE variant_id IS NOT NULL
            DO UPDATE SET
              value = EXCLUDED.value
        """),
        [
            {
                "gid": generation_id,
                "vid": variant_id,
                "name": name,
                "val": float(value),
            }
            for name, value in metrics.items()
        ],
    )

    logger.debug("Wrote metrics for variant %s (total=%d)", variant_id, counts.total)


def save_variant_counts_as_metrics(
    engine: Engine,
    variant_id: int,
    counts: "MutationCounts",
    *,
    conn: Optional[Connection] = None,
) -> None:
    """
    Saves mutation summary statistics into the metrics table.

    Looks up the variant's generation_id (foreign key) then upserts
    three derived-metric rows.  Supports standalone or shared-transaction use.

    Args:
        engine: SQLAlchemy engine instance.
        variant_id: Target variant primary key.
        counts: MutationCounts with synonymous, nonsynonymous, and total.
        conn: Optional existing connection for shared transactions.
    """
    gid = get_variant_generation_id(engine, variant_id)

    if conn is not None:
        _write_metrics(conn, variant_id, gid, counts)
    else:
        with engine.begin() as txn_conn:
            _write_metrics(txn_conn, variant_id, gid, counts)


# =============================================================================
# Experiment Run Metadata (traceability)
# =============================================================================

def _write_run_metadata(
    conn: Connection,
    experiment_id: int,
    field_name: str,
    field_value: str,
) -> None:
    """
    Upserts a single metadata key-value pair on an existing connection.

    Args:
        conn: Active SQLAlchemy connection (caller manages transaction).
        experiment_id: Owning experiment primary key.
        field_name: Metadata key (unique per experiment).
        field_value: Metadata value to store.
    """
    conn.execute(
        text("""
            INSERT INTO public.experiment_metadata
              (experiment_id, field_name, field_value)
            VALUES
              (:eid, :fname, :fval)
            ON CONFLICT (experiment_id, field_name)
            DO UPDATE SET field_value = EXCLUDED.field_value
        """),
        {
            "eid": experiment_id,
            "fname": field_name,
            "fval": field_value,
        },
    )


def save_run_metadata(
    engine: Engine,
    experiment_id: int,
    field_name: str,
    field_value: str,
    *,
    conn: Optional[Connection] = None,
) -> None:
    """
    Persists run-level metadata into experiment_metadata.By recording traceability information such as pipeline completion timestamps
    and processing parameters. 

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Owning experiment primary key.
        field_name: Metadata key (unique per experiment).
        field_value: Metadata value to store.
        conn: Optional existing connection for shared transactions.
    """
    if conn is not None:
        _write_run_metadata(conn, experiment_id, field_name, field_value)
    else:
        with engine.begin() as txn_conn:
            _write_run_metadata(txn_conn, experiment_id, field_name, field_value)

    logger.debug("Saved metadata %s=%s for experiment %s", field_name, field_value, experiment_id)


# =============================================================================
# Variant Sequence Analysis (public.variant_sequence_analysis)
# =============================================================================

def _strand_to_smallint(strand: Optional[str]) -> Optional[int]:
    """Converts 'PLUS'/'MINUS' to +1/-1 for the VSA strand column."""
    if strand is None:
        return None
    return 1 if strand.upper() == "PLUS" else -1


def _write_variant_sequence_analysis(
    conn: Connection,
    variant_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: List["MutationRecord"],
    user_id: int,
    analysis_version: str = "v1",
) -> int:
    """
    Upserts a row in variant_sequence_analysis and returns its vsa_id.

    Maps VariantSeqResult fields to dedicated columns where possible;
    remaining detail (frame, cds_dna, per-mutation breakdown for
    non-insertable types) goes into qc_flags JSONB.
    """
    qc_flags: Dict[str, Any] = {
        "has_ambiguous_bases": result.qc.has_ambiguous_bases,
        "has_frameshift": result.qc.has_frameshift,
        "notes": result.qc.notes,
        "frame": result.frame,
        "cds_dna": result.cds_dna,
        "user_id": user_id,
        "mutation_counts": {
            "synonymous": counts.synonymous,
            "nonsynonymous": counts.nonsynonymous,
            "total": counts.total,
        },
        # Preserve non-insertable mutations (FRAMESHIFT/INSERTION/DELETION)
        # that cannot satisfy the mutations table constraints.
        "non_insertable_mutations": [
            {
                "mutation_type": m.mutation_type,
                "codon_index_1based": m.codon_index_1based,
                "aa_position_1based": m.aa_position_1based,
                "wt_codon": m.wt_codon,
                "var_codon": m.var_codon,
                "wt_aa": m.wt_aa,
                "var_aa": m.var_aa,
                "notes": m.notes,
            }
            for m in mutations
            if m.mutation_type not in _INSERTABLE_MUTATION_TYPES
        ],
    }

    is_circular = (
        result.cds_start_0based is not None
        and result.cds_end_0based_excl is not None
        and result.cds_end_0based_excl < result.cds_start_0based
    )

    has_error = result.protein_aa is None
    status = "failed" if has_error else "success"
    error_msg = result.qc.notes if has_error else None

    row = conn.execute(
        text("""
            INSERT INTO public.variant_sequence_analysis
              (variant_id, analysis_version, status, error_message,
               orf_start, orf_end, is_circular_wrap, strand,
               translated_protein_sequence, has_internal_stop, qc_flags)
            VALUES
              (:vid, :ver, :status, :err,
               :orf_start, :orf_end, :circ, :strand,
               :prot, :stop, CAST(:qc AS jsonb))
            ON CONFLICT (variant_id, analysis_version)
            DO UPDATE SET
              status                      = EXCLUDED.status,
              error_message               = EXCLUDED.error_message,
              orf_start                   = EXCLUDED.orf_start,
              orf_end                     = EXCLUDED.orf_end,
              is_circular_wrap            = EXCLUDED.is_circular_wrap,
              strand                      = EXCLUDED.strand,
              translated_protein_sequence = EXCLUDED.translated_protein_sequence,
              has_internal_stop           = EXCLUDED.has_internal_stop,
              qc_flags                    = EXCLUDED.qc_flags,
              updated_at                  = now()
            RETURNING vsa_id
        """),
        {
            "vid": variant_id,
            "ver": analysis_version,
            "status": status,
            "err": error_msg,
            "orf_start": result.cds_start_0based,
            "orf_end": result.cds_end_0based_excl,
            "circ": is_circular,
            "strand": _strand_to_smallint(result.strand),
            "prot": result.protein_aa,
            "stop": result.qc.has_premature_stop,
            "qc": json.dumps(qc_flags),
        },
    ).scalar_one()

    logger.debug("Wrote VSA row vsa_id=%d for variant %s", row, variant_id)
    return int(row)


# =============================================================================
# Variant Analysis Results
# =============================================================================

def _build_analysis_payload(
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: List["MutationRecord"],
    user_id: int,
) -> Dict[str, Any]:
    """
    Produces a legacy JSONB summary stored in variants.extra_metadata.

    Most queryable data now lives in variant_sequence_analysis; this payload
    retains a denormalised snapshot for backward-compatible reads.
    """
    return {
        "user_id": user_id,
        "cds_start_0based": result.cds_start_0based,
        "cds_end_0based_excl": result.cds_end_0based_excl,
        "strand": result.strand,
        "frame": result.frame,
        "cds_dna": result.cds_dna,
        "protein_aa": result.protein_aa,
        "qc": {
            "has_ambiguous_bases": result.qc.has_ambiguous_bases,
            "has_frameshift": result.qc.has_frameshift,
            "has_premature_stop": result.qc.has_premature_stop,
            "notes": result.qc.notes,
        },
        "mutation_counts": {
            "synonymous": counts.synonymous,
            "nonsynonymous": counts.nonsynonymous,
            "total": counts.total,
        },
        "mutations": [
            {
                "mutation_type": m.mutation_type,
                "codon_index_1based": m.codon_index_1based,
                "aa_position_1based": m.aa_position_1based,
                "wt_codon": m.wt_codon,
                "var_codon": m.var_codon,
                "wt_aa": m.wt_aa,
                "var_aa": m.var_aa,
                "notes": m.notes,
            }
            for m in mutations
        ],
    }


def insert_variant_analysis(
    engine: Engine,
    *,
    variant_id: int,
    experiment_id: int,
    user_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: Iterable["MutationRecord"],
) -> None:
    """
    Persists a complete variant analysis result atomically.

    Writes to five locations in a single transaction:
        1. variant_sequence_analysis — structured analysis row.
        2. variants.protein_sequence — translated protein string.
        3. variants.extra_metadata — legacy JSONB snapshot.
        4. mutations — individual rows (linked to VSA via vsa_id).
        5. metrics — derived mutation-count metrics.
    """
    muts_list = list(mutations)
    payload = _build_analysis_payload(result, counts, muts_list, user_id)

    with engine.begin() as conn:
        # Structured analysis row (returns vsa_id for linking mutations)
        vsa_id = _write_variant_sequence_analysis(
            conn, variant_id, result, counts, muts_list, user_id,
        )

        # Update variant's protein_sequence, fetch generation_id, and keep legacy JSONB snapshot
        row = conn.execute(
            text("""
                UPDATE public.variants
                SET protein_sequence = :prot,
                    extra_metadata   = jsonb_set(
                        COALESCE(extra_metadata, CAST('{}' AS jsonb)),
                        '{sequence_analysis}',
                        CAST(:payload AS jsonb)
                    )
                WHERE variant_id = :vid
                RETURNING generation_id
            """),
            {
                "vid": variant_id,
                "prot": result.protein_aa,
                "payload": json.dumps(payload),
            },
        ).scalar_one()
        gid = int(row)

        _write_mutations(conn, variant_id, muts_list, mutation_type="protein", vsa_id=vsa_id)
        _write_metrics(conn, variant_id, gid, counts)

    logger.debug(
        "Persisted analysis for variant %s (experiment %s, vsa_id=%d, %d mutations)",
        variant_id, experiment_id, vsa_id, len(muts_list),
    )


# =============================================================================
# End-to-End Persistence 
# =============================================================================

def persist_full_variant_analysis(
    engine: Engine,
    experiment_id: int,
    variant_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: Iterable["MutationRecord"],
) -> None:
    """
    Persists mutations, VSA row, metrics, and run metadata atomically.

    Args:
        engine: SQLAlchemy engine instance.
        experiment_id: Owning experiment primary key.
        variant_id: Variant being persisted.
        result: VariantSeqResult from sequence processing.
        counts: MutationCounts.
        mutations: Individual MutationRecord instances to store.
    """
    muts_list = list(mutations)

    with engine.begin() as conn:
        vsa_id = _write_variant_sequence_analysis(
            conn, variant_id, result, counts, muts_list,
            user_id=0,  # unknown at this call site
        )
        replace_variant_mutations(
            engine, variant_id, muts_list, conn=conn,
        )
        # Back-fill vsa_id on the mutation rows just written
        conn.execute(
            text("""
                UPDATE public.mutations
                SET vsa_id = :vsa
                WHERE variant_id = :vid AND mutation_type = 'protein'
            """),
            {"vsa": vsa_id, "vid": variant_id},
        )
        save_variant_counts_as_metrics(
            engine, variant_id, counts, conn=conn,
        )
        save_run_metadata(
            engine,
            experiment_id,
            field_name="last_sequence_processing_run",
            field_value="completed",
            conn=conn,
        )

    logger.info(
        "Persisted full analysis for variant %s (experiment %s, vsa_id=%d)",
        variant_id, experiment_id, vsa_id,
    )


# =============================================================================
# Batch Persistence (multiple variants in one transaction)
# =============================================================================

@dataclasses.dataclass
class VariantAnalysisItem:
    """A single variant's analysis results, ready for batch persistence."""
    variant_id: int
    result: "VariantSeqResult"
    counts: "MutationCounts"
    mutations: List["MutationRecord"]


def insert_variant_analyses_batch(
    engine: Engine,
    *,
    experiment_id: int,
    user_id: int,
    items: List[VariantAnalysisItem],
) -> None:
    """
    Persists analysis results for multiple variants in a single transaction.

    Compared to calling insert_variant_analysis() in a loop, this:
      - Opens one DB connection/transaction instead of N
      - Pre-fetches all generation_ids in a single query
      - Reduces total round-trips from ~6N to ~3N+2
    """
    if not items:
        return

    variant_ids = [it.variant_id for it in items]

    with engine.begin() as conn:
        # Bulk-fetch generation_ids for all variants in one query
        rows = conn.execute(
            text("""
                SELECT variant_id, generation_id
                FROM public.variants
                WHERE variant_id = ANY(:vids)
            """),
            {"vids": variant_ids},
        ).fetchall()
        gid_map = {int(r[0]): int(r[1]) for r in rows}

        for it in items:
            muts_list = list(it.mutations)
            payload = _build_analysis_payload(it.result, it.counts, muts_list, user_id)

            vsa_id = _write_variant_sequence_analysis(
                conn, it.variant_id, it.result, it.counts, muts_list, user_id,
            )

            conn.execute(
                text("""
                    UPDATE public.variants
                    SET protein_sequence = :prot,
                        extra_metadata   = jsonb_set(
                            COALESCE(extra_metadata, CAST('{}' AS jsonb)),
                            '{sequence_analysis}',
                            CAST(:payload AS jsonb)
                        )
                    WHERE variant_id = :vid
                """),
                {
                    "vid": it.variant_id,
                    "prot": it.result.protein_aa,
                    "payload": json.dumps(payload),
                },
            )

            _write_mutations(conn, it.variant_id, muts_list, mutation_type="protein", vsa_id=vsa_id)

            gid = gid_map.get(it.variant_id)
            if gid is not None:
                _write_metrics(conn, it.variant_id, gid, it.counts)

    logger.info(
        "Batch-persisted %d variant analyses for experiment %s",
        len(items), experiment_id,
    )
