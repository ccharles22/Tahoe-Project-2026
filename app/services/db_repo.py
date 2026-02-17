from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

if TYPE_CHECKING:
    from app.services.sequence_service import WTMapping, VariantSeqResult, MutationRecord, MutationCounts


# =============================================================================
# Engine
# =============================================================================

def get_engine() -> Engine:
    """Creates an SQLAlchemy engine for PostgreSQL."""
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        future=True,
    )


# =============================================================================
# Experiment + WT reference
# =============================================================================

def get_experiment_user_and_wt(engine: Engine, experiment_id: int) -> Tuple[int, int]:
    """Acquires the user_id and wt_id for an experiment."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT user_id, wt_id
                FROM experiments
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()

    if not row:
        raise ValueError(f"Experiment not found: experiment_id={experiment_id}")

    return int(row[0]), int(row[1])


def get_wt_reference(engine: Engine, experiment_id: int) -> Tuple[str, str]:
    """
    Load WT protein and plasmid DNA required for sequence analysis.

    Returns:
        (wt_protein_aa, wt_plasmid_dna)
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT w.amino_acid_sequence, w.plasmid_sequence
                FROM experiments e
                JOIN wild_type_proteins w ON w.wt_id = e.wt_id
                WHERE e.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()

    if not row:
        raise ValueError(f"WT reference not found for experiment_id={experiment_id}")

    return str(row[0]), str(row[1])


def get_experiment_uniprot_from_wt(engine: Engine, experiment_id: int) -> Optional[str]:
    """Returns UniProt accession stored on wild_type_proteins for an experiment (or None)."""
    with engine.connect() as conn:
        acc = conn.execute(
            text("""
                SELECT w.uniprot_id
                FROM experiments e
                JOIN wild_type_proteins w ON w.wt_id = e.wt_id
                WHERE e.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).scalar_one_or_none()
    return str(acc) if acc else None


# =============================================================================
# Variant loading
# =============================================================================

def list_variants_by_experiment(engine: Engine, experiment_id: int) -> List[Tuple[int, str]]:
    """
    Obtains all the variant plasmid sequences for a given experiment.

    Returns:
        List[(variant_id, assembled_dna_sequence)]
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT v.variant_id, v.assembled_dna_sequence
                FROM variants v
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                ORDER BY v.variant_id
            """),
            {"eid": experiment_id},
        ).fetchall()

    return [(int(r[0]), str(r[1])) for r in rows]


# =============================================================================
# UniProt staging (experiment_uniprot_staging)
# =============================================================================

def upsert_uniprot_staging(
    engine: Engine,
    experiment_id: int,
    user_id: int,
    accession: str,
    protein_sequence: str,
) -> None:
    """
    Stores UniProt fetch results per (experiment_id, user_id).

    Uses UPSERT to avoid overwriting other users and to keep the latest values for this user.
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO experiment_uniprot_staging (
                    experiment_id, user_id, accession, protein_sequence, retrieved_at
                )
                VALUES (:eid, :uid, :acc, :protein, CURRENT_TIMESTAMP)
                ON CONFLICT (experiment_id, user_id)
                DO UPDATE SET
                    accession = EXCLUDED.accession,
                    protein_sequence = EXCLUDED.protein_sequence,
                    retrieved_at = EXCLUDED.retrieved_at
            """),
            {"eid": experiment_id, "uid": user_id, "acc": accession, "protein": protein_sequence},
        )


def load_uniprot_staging(
    engine: Engine,
    experiment_id: int,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    """Load UniProt staging row for (experiment_id, user_id)."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT accession, protein_sequence, retrieved_at
                FROM experiment_uniprot_staging
                WHERE experiment_id = :eid AND user_id = :uid
            """),
            {"eid": experiment_id, "uid": user_id},
        ).fetchone()

    if not row:
        return None

    return {"accession": row[0], "protein_sequence": row[1], "retrieved_at": row[2]}


# =============================================================================
# WT mapping cache (experiment_wt_mapping)
# =============================================================================

def upsert_wt_mapping(
    engine: Engine,
    experiment_id: int,
    user_id: int,
    mapping: "WTMapping",
) -> None:
    """
    Cache WT mapping per (experiment_id, user_id) into experiment_wt_mapping.mapping_json (JSONB).
    """
    payload = {
        "strand": mapping.strand,
        "frame": mapping.frame,
        "cds_start_0based": mapping.cds_start_0based,
        "cds_end_0based_excl": mapping.cds_end_0based_excl,
        "wt_cds_dna": mapping.wt_cds_dna,
        "wt_protein_aa": mapping.wt_protein_aa,
        "match_identity_pct": mapping.match_identity_pct,
        "alignment_score": mapping.alignment_score,
        "validation_status": "VALID",
    }

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO experiment_wt_mapping (
                    experiment_id, user_id, mapping_json, mapped_at
                )
                VALUES (:eid, :uid, :js::jsonb, CURRENT_TIMESTAMP)
                ON CONFLICT (experiment_id, user_id)
                DO UPDATE SET
                    mapping_json = EXCLUDED.mapping_json,
                    mapped_at = EXCLUDED.mapped_at
            """),
            {"eid": experiment_id, "uid": user_id, "js": json.dumps(payload, ensure_ascii=False)},
        )


def load_wt_mapping(
    engine: Engine,
    experiment_id: int,
    user_id: int,
) -> Optional["WTMapping"]:
    """
    Loads cached WT mapping for (experiment_id, user_id).
    Returns WTMapping if present and VALID, else None.
    """
    with engine.connect() as conn:
        mapping_json = conn.execute(
            text("""
                SELECT mapping_json
                FROM experiment_wt_mapping
                WHERE experiment_id = :eid AND user_id = :uid
            """),
            {"eid": experiment_id, "uid": user_id},
        ).scalar_one_or_none()

    if not mapping_json:
        return None

    data = mapping_json if isinstance(mapping_json, dict) else json.loads(mapping_json)
    if data.get("validation_status") != "VALID":
        return None

    from app.services.sequence_service import WTMapping  # local import to avoid cycles

    return WTMapping(
        strand=str(data["strand"]),
        frame=int(data["frame"]),
        cds_start_0based=int(data["cds_start_0based"]),
        cds_end_0based_excl=int(data["cds_end_0based_excl"]),
        wt_cds_dna=str(data["wt_cds_dna"]),
        wt_protein_aa=str(data["wt_protein_aa"]),
        match_identity_pct=float(data["match_identity_pct"]),
        alignment_score=float(data["alignment_score"]),
    )


# =============================================================================
# Variant analysis history (variant_sequence_analysis + variant_mutations)
# =============================================================================

def insert_variant_analysis(
    engine: Engine,
    *,
    variant_id: int,
    experiment_id: int,
    user_id: int,
    result: "VariantSeqResult",
    counts: "MutationCounts",
    mutations: Optional[Iterable["MutationRecord"]] = None,
    also_set_variants_protein_sequence: bool = False,
) -> int:
    """
    Inserts a NEW analysis row (history) for (variant_id, user_id).
    Returns the new analysis_id.

    - analysis_json stored as JSONB
    - optional mutations stored in variant_mutations linked by analysis_id
    - optionally sets variants.protein_sequence (off by default to avoid teammate collisions)
    """
    analysis_payload: Dict[str, Any] = {
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
        "counts": {
            "synonymous": counts.synonymous,
            "nonsynonymous": counts.nonsynonymous,
            "total": counts.total,
        },
    }

    analysis_json = json.dumps(analysis_payload, ensure_ascii=False)

    with engine.begin() as conn:
        # Inserts analysis row and return analysis_id
        analysis_id = conn.execute(
            text("""
                INSERT INTO variant_sequence_analysis (
                    variant_id, experiment_id, user_id, analysis_json, analysed_at
                )
                VALUES (:vid, :eid, :uid, :js::jsonb, CURRENT_TIMESTAMP)
                RETURNING analysis_id
            """),
            {"vid": variant_id, "eid": experiment_id, "uid": user_id, "js": analysis_json},
        ).scalar_one()

        # Inserts mutations if provided (can be empty or None)
        if mutations is not None:
            for m in mutations:
                conn.execute(
                    text("""
                        INSERT INTO variant_mutations (
                            analysis_id,
                            mutation_type,
                            codon_index_1based,
                            aa_position_1based,
                            wt_codon,
                            var_codon,
                            wt_aa,
                            var_aa,
                            notes
                        )
                        VALUES (
                            :aid,
                            :mtype,
                            :codon_idx,
                            :aa_pos,
                            :wt_codon,
                            :var_codon,
                            :wt_aa,
                            :var_aa,
                            :notes
                        )
                    """),
                    {
                        "aid": analysis_id,
                        "mtype": m.mutation_type,
                        "codon_idx": m.codon_index_1based,
                        "aa_pos": m.aa_position_1based,
                        "wt_codon": m.wt_codon,
                        "var_codon": m.var_codon,
                        "wt_aa": m.wt_aa,
                        "var_aa": m.var_aa,
                        "notes": m.notes,
                    },
                )

        # Optional: write protein_sequence onto variants table (can collide across users)
        if also_set_variants_protein_sequence:
            conn.execute(
                text("""
                    UPDATE variants
                    SET protein_sequence = :protein
                    WHERE variant_id = :vid
                """),
                {"protein": result.protein_aa, "vid": variant_id},
            )

    return int(analysis_id)


def load_latest_variant_analysis(
    engine: Engine,
    *,
    variant_id: int,
    user_id: int,
    include_mutations: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Loads the latest analysis for the variant_id and user_id).
    If include_mutations=True, returns a 'mutations' list too.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT analysis_id, experiment_id, analysed_at, analysis_json
                FROM variant_sequence_analysis
                WHERE variant_id = :vid AND user_id = :uid
                ORDER BY analysed_at DESC, analysis_id DESC
                LIMIT 1
            """),
            {"vid": variant_id, "uid": user_id},
        ).fetchone()

        if not row:
            return None

        analysis_id = int(row[0])
        analysis_json = row[3] if isinstance(row[3], dict) else json.loads(row[3])

        out: Dict[str, Any] = {
            "analysis_id": analysis_id,
            "variant_id": int(variant_id),
            "experiment_id": int(row[1]),
            "user_id": int(user_id),
            "analysed_at": row[2],
            "analysis_json": analysis_json,
        }

        if include_mutations:
            muts = conn.execute(
                text("""
                    SELECT
                      mutation_id,
                      mutation_type,
                      codon_index_1based,
                      aa_position_1based,
                      wt_codon,
                      var_codon,
                      wt_aa,
                      var_aa,
                      notes
                    FROM variant_mutations
                    WHERE analysis_id = :aid
                    ORDER BY mutation_id
                """),
                {"aid": analysis_id},
            ).fetchall()

            out["mutations"] = [
                {
                    "mutation_id": int(m[0]),
                    "mutation_type": m[1],
                    "codon_index_1based": m[2],
                    "aa_position_1based": m[3],
                    "wt_codon": m[4],
                    "var_codon": m[5],
                    "wt_aa": m[6],
                    "var_aa": m[7],
                    "notes": m[8],
                }
                for m in muts
            ]

    return out


def delete_analysis(engine: Engine, analysis_id: int) -> None:
    """
    Deletes a single analysis row from variant_sequence_analysis due to
    foreign key constraints with variant_mutations .
    """
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM variant_sequence_analysis WHERE analysis_id = :aid"),
            {"aid": analysis_id},
        )


# =============================================================================
# Status tracking
# =============================================================================

def update_experiment_status(engine: Engine, experiment_id: int, status: str) -> None:
    """Updates experiments.analysis_status."""
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE experiments
                SET analysis_status = :status
                WHERE experiment_id = :eid
            """),
            {"status": status, "eid": experiment_id},
        )
