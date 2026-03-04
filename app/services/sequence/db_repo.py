"""
Database repository layer for the sequence processing pipeline.

NON-DESTRUCTIVE DEFAULTS:
- This repository is intentionally "append / set-once" by default.
- It avoids overwriting or deleting existing analysis results unless explicitly
  requested via overwrite=True.

This behavior matches a "do not overwrite existing DB state" policy while keeping
your existing schema unchanged.

Tables touched:
- experiment_metadata (wt_mapping_json, uniprot_staging, run metadata keys)
- variants (protein_sequence, extra_metadata->sequence_analysis)
- variant_sequence_analysis (unique by variant_id + analysis_version)
- mutations (unique by variant_id + mutation_type + position + original + mutated)
- metrics (unique indexes already exist; we avoid overwriting unless overwrite=True)
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

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
# Others (FRAMESHIFT / INSERTION / DELETION) are carried in JSON payloads.
_INSERTABLE_MUTATION_TYPES = {"SYNONYMOUS", "NONSYNONYMOUS", "NONSENSE", "AMBIGUOUS"}


# =============================================================================
# Engine
# =============================================================================

def get_engine() -> Engine:
    """Build the shared SQLAlchemy engine for sequence-processing work."""
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True, future=True)


# =============================================================================
# WT Reference
# =============================================================================

def get_wt_reference(engine: Engine, experiment_id: int) -> Tuple[str, str]:
    """Return the WT protein and plasmid sequence for one experiment."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT w.amino_acid_sequence, w.plasmid_sequence, e.extra_metadata
                FROM public.experiments e
                JOIN public.wild_type_proteins w
                  ON w.wt_id = e.wt_id
                WHERE e.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()

        staged = conn.execute(
            text("""
                SELECT field_value
                FROM public.experiment_metadata
                WHERE experiment_id = :eid
                  AND field_name = 'uniprot_staging'
            """),
            {"eid": experiment_id},
        ).fetchone()

    if not row:
        raise ValueError(f"No WT reference found for experiment_id={experiment_id}")

    wt_protein = str(row[0])
    wt_plasmid = str(row[1])
    exp_meta_raw = row[2] if len(row) > 2 else None

    exp_meta: Optional[Dict[str, Any]] = None
    if isinstance(exp_meta_raw, dict):
        exp_meta = exp_meta_raw
    elif isinstance(exp_meta_raw, str) and exp_meta_raw.strip():
        try:
            loaded = json.loads(exp_meta_raw)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            exp_meta = loaded

    if exp_meta:
        plasmid_override = exp_meta.get("wt_plasmid_sequence")
        if isinstance(plasmid_override, str) and plasmid_override.strip():
            cleaned = "".join(plasmid_override.split()).upper()
            # Only apply the override when it is longer than the DB value.
            # A CDS-only override (len == aa_len * 3) would disable the
            # backbone-anchor remap optimisation that needs the full plasmid.
            if len(cleaned) > len(wt_plasmid):
                wt_plasmid = cleaned

    if staged and staged[0]:
        try:
            payload = json.loads(staged[0])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            staged_protein = payload.get("protein_sequence")
            if isinstance(staged_protein, str) and staged_protein.strip():
                wt_protein = staged_protein.strip().upper()

    return wt_protein, wt_plasmid


# =============================================================================
# Experiment helpers
# =============================================================================

def get_experiment_user_and_wt(engine: Engine, experiment_id: int) -> Tuple[int, int]:
    """Return the owning user id and WT id for an experiment."""
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


def update_experiment_status(engine: Engine, experiment_id: int, status: str) -> None:
    """Persist the current analysis status for an experiment."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE public.experiments
                SET analysis_status = :status
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id, "status": status},
        )


def get_experiment_status(engine: Engine, experiment_id: int) -> Optional[str]:
    """Read the current analysis status for an experiment."""
    with engine.connect() as conn:
        status = conn.execute(
            text("""
                SELECT analysis_status
                FROM public.experiments
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).scalar_one_or_none()
    return str(status) if status is not None else None


# =============================================================================
# Variants
# =============================================================================

def list_variants_by_experiment(engine: Engine, experiment_id: int) -> List[Tuple[int, str]]:
    """List variant ids and assembled DNA for one experiment."""
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

    return [(int(r[0]), str(r[1])) for r in rows if r[1] is not None]


def list_processed_variant_ids(engine: Engine, experiment_id: int) -> set:
    """
    "Processed" is defined as having protein_sequence set.
    With non-destructive defaults, this stays stable after first successful run.
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
    """Resolve the generation id that owns a given variant."""
    with engine.connect() as conn:
        gid = conn.execute(
            text("SELECT generation_id FROM public.variants WHERE variant_id = :vid"),
            {"vid": variant_id},
        ).scalar_one_or_none()

    if gid is None:
        raise ValueError(f"Variant not found: {variant_id}")

    return int(gid)


# =============================================================================
# experiment_metadata helpers (non-destructive by default)
# =============================================================================

def _upsert_experiment_metadata(
    conn: Connection,
    experiment_id: int,
    field_name: str,
    field_value: str,
    *,
    overwrite: bool,
) -> None:
    """
    Your schema: unique(experiment_id, field_name).
    overwrite=False => set-once (DO NOTHING on conflict)
    overwrite=True  => update field_value
    """
    sql = """
        INSERT INTO public.experiment_metadata
          (experiment_id, field_name, field_value)
        VALUES
          (:eid, :fname, :fval)
        ON CONFLICT (experiment_id, field_name)
    """
    sql += "DO UPDATE SET field_value = EXCLUDED.field_value" if overwrite else "DO NOTHING"

    conn.execute(text(sql), {"eid": experiment_id, "fname": field_name, "fval": field_value})


# =============================================================================
# WT Mapping Cache (experiment_metadata)
# =============================================================================

def load_wt_mapping(engine: Engine, experiment_id: int, user_id: int) -> Optional["WTMapping"]:
    """Load a cached WT mapping from experiment metadata if present."""
    from app.services.sequence.sequence_service import WTMapping  # avoid circular import

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
        return None

    data: Dict[str, Any] = json.loads(row[0])
    data.pop("user_id", None)
    return WTMapping(**data)


def upsert_wt_mapping(
    engine: Engine,
    experiment_id: int,
    user_id: int,
    wt_mapping: "WTMapping",
    *,
    overwrite: bool = False,
) -> None:
    """Persist the WT mapping cache in experiment metadata."""
    mapping_dict = dataclasses.asdict(wt_mapping)
    mapping_dict["user_id"] = user_id

    with engine.begin() as conn:
        _upsert_experiment_metadata(
            conn,
            experiment_id,
            "wt_mapping_json",
            json.dumps(mapping_dict),
            overwrite=overwrite,
        )


def upsert_uniprot_staging(
    engine: Engine,
    experiment_id: int,
    user_id: int,
    accession: str,
    protein_sequence: str,
    *,
    overwrite: bool = False,
) -> None:
    """Persist staged UniProt WT data for the staging workflow."""
    payload = json.dumps({
        "user_id": user_id,
        "accession": accession,
        "protein_sequence": protein_sequence,
    })
    with engine.begin() as conn:
        _upsert_experiment_metadata(
            conn, experiment_id, "uniprot_staging", payload, overwrite=overwrite
        )


def has_uniprot_staging(engine: Engine, experiment_id: int) -> bool:
    """Return whether staged UniProt WT data exists for this experiment."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT field_value
                FROM public.experiment_metadata
                WHERE experiment_id = :eid
                  AND field_name = 'uniprot_staging'
            """),
            {"eid": experiment_id},
        ).fetchone()
    return bool(row and row[0])


def clear_wt_mapping_cache(engine: Engine, experiment_id: int) -> None:
    """Remove any cached WT mapping so it is recomputed on the next run."""
    with engine.begin() as conn:
        _upsert_experiment_metadata(
            conn,
            experiment_id,
            "wt_mapping_json",
            "",
            overwrite=True,
        )


def save_run_metadata(
    engine: Engine,
    experiment_id: int,
    field_name: str,
    field_value: str,
    *,
    overwrite: bool = False,
    conn: Optional[Connection] = None,
) -> None:
    """Persist summary metadata about the most recent sequence-processing run."""
    if conn is not None:
        _upsert_experiment_metadata(conn, experiment_id, field_name, field_value, overwrite=overwrite)
    else:
        with engine.begin() as txn_conn:
            _upsert_experiment_metadata(txn_conn, experiment_id, field_name, field_value, overwrite=overwrite)


# =============================================================================
# Mutations (public.mutations)
# =============================================================================

def _write_mutations(
    conn: Connection,
    variant_id: int,
    mutations: Iterable["MutationRecord"],
    mutation_type: str = "protein",
    vsa_id: Optional[int] = None,
    *,
    overwrite: bool = False,
) -> int:
    """
    overwrite=False:
      - NEVER deletes existing mutation rows
      - inserts new rows, skips conflicts (DO NOTHING)

    overwrite=True:
      - deletes existing rows for (variant_id, mutation_type)
      - re-inserts, updating duplicates (DO UPDATE)
    """
    muts = list(mutations)

    if overwrite:
        conn.execute(
            text("""
                DELETE FROM public.mutations
                WHERE variant_id = :vid
                  AND mutation_type = :mt
            """),
            {"vid": variant_id, "mt": mutation_type},
        )

    batch_params: List[Dict[str, Any]] = []
    skipped = 0

    for m in muts:
        # Skip mutation types that cannot fit the mutations table constraints
        if m.mutation_type not in _INSERTABLE_MUTATION_TYPES:
            skipped += 1
            continue

        # Protein table should only store AA changes; synonymous codon changes
        # don't change AA so they shouldn't be in protein-scope mutation rows.
        if mutation_type == "protein" and m.mutation_type == "SYNONYMOUS":
            skipped += 1
            continue

        if m.aa_position_1based is None or m.wt_aa is None or m.var_aa is None:
            skipped += 1
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

    if not batch_params:
        if skipped:
            logger.debug("Variant %s: no insertable mutations (%d skipped).", variant_id, skipped)
        return 0

    conflict_sql = """
        ON CONFLICT (variant_id, mutation_type, position, original, mutated)
    """
    conflict_sql += """
        DO UPDATE SET
          is_synonymous = EXCLUDED.is_synonymous,
          annotation    = EXCLUDED.annotation,
          vsa_id        = EXCLUDED.vsa_id
    """ if overwrite else "DO NOTHING"

    conn.execute(
        text(f"""
            INSERT INTO public.mutations
              (variant_id, mutation_type, position,
               original, mutated, is_synonymous, annotation, vsa_id)
            VALUES
              (:vid, :mt, :pos, :orig, :mut, :syn, :ann, :vsa)
            {conflict_sql}
        """),
        batch_params,
    )

    if skipped:
        logger.debug(
            "Variant %s: inserted %d mutations (%d skipped).",
            variant_id, len(batch_params), skipped,
        )

    return len(batch_params)


def replace_variant_mutations(
    engine: Engine,
    variant_id: int,
    mutations: Iterable["MutationRecord"],
    mutation_type: str = "protein",
    *,
    conn: Optional[Connection] = None,
    overwrite: bool = False,
    vsa_id: Optional[int] = None,
) -> None:
    """
    Backward compatible name, but non-destructive by default unless overwrite=True.
    """
    if conn is not None:
        _write_mutations(conn, variant_id, mutations, mutation_type, vsa_id=vsa_id, overwrite=overwrite)
    else:
        with engine.begin() as txn_conn:
            _write_mutations(txn_conn, variant_id, mutations, mutation_type, vsa_id=vsa_id, overwrite=overwrite)


# =============================================================================
# Metrics (public.metrics)
# =============================================================================

def _write_metrics(
    conn: Connection,
    variant_id: int,
    generation_id: int,
    counts: "MutationCounts",
    *,
    overwrite: bool = False,
) -> None:
    """
    overwrite=False: DO NOTHING on conflicts (set-once).
    overwrite=True : DO UPDATE (latest-wins).
    """
    metrics = {
        "mutation_synonymous_count": counts.synonymous,
        "mutation_nonsynonymous_count": counts.nonsynonymous,
        "mutation_total_count": counts.total,
    }

    conflict_sql = """
        ON CONFLICT (generation_id, variant_id, metric_name, metric_type)
          WHERE variant_id IS NOT NULL
    """
    conflict_sql += "DO UPDATE SET value = EXCLUDED.value" if overwrite else "DO NOTHING"

    conn.execute(
        text(f"""
            INSERT INTO public.metrics
              (generation_id, variant_id,
               metric_name, metric_type,
               value, unit)
            VALUES
              (:gid, :vid,
               :name, 'derived',
               :val, 'count')
            {conflict_sql}
        """),
        [
            {"gid": generation_id, "vid": variant_id, "name": k, "val": float(v)}
            for k, v in metrics.items()
        ],
    )


def save_variant_counts_as_metrics(
    engine: Engine,
    variant_id: int,
    counts: "MutationCounts",
    *,
    conn: Optional[Connection] = None,
    overwrite: bool = False,
) -> None:
    """Store sequence-derived mutation counts as per-variant derived metrics."""
    gid = get_variant_generation_id(engine, variant_id)
    if conn is not None:
        _write_metrics(conn, variant_id, gid, counts, overwrite=overwrite)
    else:
        with engine.begin() as txn_conn:
            _write_metrics(txn_conn, variant_id, gid, counts, overwrite=overwrite)


# =============================================================================
# Variant Sequence Analysis (public.variant_sequence_analysis)
# =============================================================================

def _strand_to_smallint(strand: Optional[str]) -> Optional[int]:
    if strand is None:
        return None
    return 1 if strand.upper() == "PLUS" else -1


def _get_existing_vsa_id(conn: Connection, variant_id: int, analysis_version: str) -> Optional[int]:
    return conn.execute(
        text("""
            SELECT vsa_id
            FROM public.variant_sequence_analysis
            WHERE variant_id = :vid AND analysis_version = :ver
        """),
        {"vid": variant_id, "ver": analysis_version},
    ).scalar_one_or_none()


def _write_variant_sequence_analysis(
    conn: Connection,
    variant_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: List["MutationRecord"],
    user_id: int,
    analysis_version: str = "v1",
    *,
    overwrite: bool = False,
) -> int:
    qc_flags: Dict[str, Any] = {
        "has_ambiguous_bases": result.qc.has_ambiguous_bases,
        "has_frameshift": result.qc.has_frameshift,
        "has_premature_stop": result.qc.has_premature_stop,
        "notes": result.qc.notes,
        "frame": result.frame,
        "cds_dna": result.cds_dna,
        "user_id": user_id,
        "mutation_counts": {
            "synonymous": counts.synonymous,
            "nonsynonymous": counts.nonsynonymous,
            "total": counts.total,
        },
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

    base_sql = """
        INSERT INTO public.variant_sequence_analysis
          (variant_id, analysis_version, status, error_message,
           orf_start, orf_end, is_circular_wrap, strand,
           translated_protein_sequence, has_internal_stop, qc_flags)
        VALUES
          (:vid, :ver, :status, :err,
           :orf_start, :orf_end, :circ, :strand,
           :prot, :stop, CAST(:qc AS jsonb))
        ON CONFLICT (variant_id, analysis_version)
    """

    if overwrite:
        conflict = """
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
        """
    else:
        # Non-destructive default: if row exists, do nothing and return existing vsa_id
        conflict = "DO NOTHING RETURNING vsa_id"

    params = {
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
    }

    vsa_id = conn.execute(text(base_sql + conflict), params).scalar_one_or_none()
    if vsa_id is None:
        existing = _get_existing_vsa_id(conn, variant_id, analysis_version)
        if existing is None:
            # This should not happen unless the insert failed in a surprising way
            raise RuntimeError("Failed to create or load variant_sequence_analysis row.")
        return int(existing)

    return int(vsa_id)


# =============================================================================
# Analysis Payload (variants.extra_metadata)
# =============================================================================

def _build_analysis_payload(
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: List["MutationRecord"],
    user_id: int,
) -> Dict[str, Any]:
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


def _update_variant_outputs(
    conn: Connection,
    variant_id: int,
    protein_sequence: Optional[str],
    payload_json: str,
    *,
    overwrite: bool,
) -> int:
    """
    Non-destructive by default:
      - protein_sequence is set only if currently NULL, unless overwrite=True
      - extra_metadata.sequence_analysis is set only if missing, unless overwrite=True

    Returns generation_id for downstream metric writes.
    """
    row = conn.execute(
        text("""
            UPDATE public.variants
            SET protein_sequence = CASE
                    WHEN :overwrite THEN :prot
                    ELSE COALESCE(protein_sequence, :prot)
                END,
                extra_metadata = CASE
                    WHEN :overwrite THEN jsonb_set(
                        CASE
                            WHEN jsonb_typeof(extra_metadata) = 'object' THEN extra_metadata
                            ELSE CAST('{}' AS jsonb)
                        END,
                        '{sequence_analysis}',
                        CAST(:payload AS jsonb)
                    )
                    WHEN (extra_metadata->'sequence_analysis') IS NULL THEN jsonb_set(
                        CASE
                            WHEN jsonb_typeof(extra_metadata) = 'object' THEN extra_metadata
                            ELSE CAST('{}' AS jsonb)
                        END,
                        '{sequence_analysis}',
                        CAST(:payload AS jsonb)
                    )
                    ELSE extra_metadata
                END
            WHERE variant_id = :vid
            RETURNING generation_id
        """),
        {
            "vid": variant_id,
            "prot": protein_sequence,
            "payload": payload_json,
            "overwrite": overwrite,
        },
    ).scalar_one()
    return int(row)


# =============================================================================
# Public persistence API
# =============================================================================

def insert_variant_analysis(
    engine: Engine,
    *,
    variant_id: int,
    experiment_id: int,
    user_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: Iterable["MutationRecord"],
    analysis_version: str = "v1",
    overwrite: bool = False,
) -> None:
    """
    Persists a complete variant analysis result.

    overwrite=False (default): set-once behavior; avoids overwriting previous results.
    overwrite=True: latest-wins behavior; replaces values for this analysis_version.
    """
    muts_list = list(mutations)
    payload = _build_analysis_payload(result, counts, muts_list, user_id)

    with engine.begin() as conn:
        vsa_id = _write_variant_sequence_analysis(
            conn,
            variant_id,
            result,
            counts,
            muts_list,
            user_id,
            analysis_version=analysis_version,
            overwrite=overwrite,
        )

        gid = _update_variant_outputs(
            conn,
            variant_id,
            result.protein_aa,
            json.dumps(payload),
            overwrite=overwrite,
        )

        # Mutations: non-destructive unless overwrite=True
        _write_mutations(
            conn,
            variant_id,
            muts_list,
            mutation_type="protein",
            vsa_id=vsa_id,
            overwrite=overwrite,
        )

        # Metrics: non-destructive unless overwrite=True
        _write_metrics(
            conn,
            variant_id,
            gid,
            counts,
            overwrite=overwrite,
        )

    logger.info(
        "Persisted analysis for variant %s (experiment %s, analysis_version=%s, overwrite=%s)",
        variant_id, experiment_id, analysis_version, overwrite,
    )


def persist_full_variant_analysis(
    engine: Engine,
    experiment_id: int,
    variant_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: Iterable["MutationRecord"],
    *,
    user_id: int,
    analysis_version: str = "v1",
    overwrite: bool = False,
) -> None:
    """
    End-to-end persistence in one transaction.
    """
    muts_list = list(mutations)
    payload = _build_analysis_payload(result, counts, muts_list, user_id)

    with engine.begin() as conn:
        vsa_id = _write_variant_sequence_analysis(
            conn,
            variant_id,
            result,
            counts,
            muts_list,
            user_id,
            analysis_version=analysis_version,
            overwrite=overwrite,
        )

        gid = _update_variant_outputs(
            conn,
            variant_id,
            result.protein_aa,
            json.dumps(payload),
            overwrite=overwrite,
        )

        _write_mutations(conn, variant_id, muts_list, mutation_type="protein", vsa_id=vsa_id, overwrite=overwrite)
        _write_metrics(conn, variant_id, gid, counts, overwrite=overwrite)

        # Run metadata: non-destructive unless overwrite=True
        save_run_metadata(
            engine,
            experiment_id,
            field_name="last_sequence_processing_run",
            field_value="completed",
            conn=conn,
            overwrite=overwrite,
        )

    logger.info(
        "Persisted full analysis for variant %s (experiment %s, analysis_version=%s, overwrite=%s)",
        variant_id, experiment_id, analysis_version, overwrite,
    )


# =============================================================================
# Batch Persistence (multiple variants in one transaction)
# =============================================================================

@dataclasses.dataclass
class VariantAnalysisItem:
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
    analysis_version: str = "v1",
    overwrite: bool = False,
) -> None:
    """Write a batch of sequence-analysis payloads, mutations, and derived metrics."""
    if not items:
        return

    variant_ids = [it.variant_id for it in items]

    with engine.begin() as conn:
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
                conn,
                it.variant_id,
                it.result,
                it.counts,
                muts_list,
                user_id,
                analysis_version=analysis_version,
                overwrite=overwrite,
            )

            gid = gid_map.get(it.variant_id)
            if gid is None:
                gid = _update_variant_outputs(
                    conn,
                    it.variant_id,
                    it.result.protein_aa,
                    json.dumps(payload),
                    overwrite=overwrite,
                )
            else:
                # still update outputs even if we already know gid
                _update_variant_outputs(
                    conn,
                    it.variant_id,
                    it.result.protein_aa,
                    json.dumps(payload),
                    overwrite=overwrite,
                )

            _write_mutations(conn, it.variant_id, muts_list, mutation_type="protein", vsa_id=vsa_id, overwrite=overwrite)

            gid_final = gid_map.get(it.variant_id, gid)
            if gid_final is not None:
                _write_metrics(conn, it.variant_id, int(gid_final), it.counts, overwrite=overwrite)

    logger.info(
        "Batch-persisted %d analyses for experiment %s (analysis_version=%s, overwrite=%s)",
        len(items), experiment_id, analysis_version, overwrite,
    )
