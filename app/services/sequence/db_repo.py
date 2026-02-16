"""
PostgreSQL repository service module.
This module is where the raw SQL and database access occur

Design principles:
- no biological logic here; (handled in app/services/sequence/sequence_service)
- no Flask-specific code here
- Deterministic, idempotent database writes

"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Tuple, List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.services.sequence.sequence_service import (
    WTMapping,
    VariantSeqResult,
    MutationRecord,
    MutationCounts,
)

# Engine/connection handling
def get_engine() -> Engine:
    """
    Constructs and returns a SQLAlchemy engine that's bound to postgreSQL.

    pool_pre_ping is enabled to help with dropped connections so that long
    running processes don't fail due to connection timeouts.
    """
    return create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        future=True,
    )

# UniProt WT protein staging
def save_staged_wt_protein(
        engine: Engine,
        experiment_id: int,
        uniprot_accession: str,
        wt_protein_sequence: str,
) -> None:
    """
    Persist the UniProt-derived WT protein sequence for an experiment.

    This function is triggered only during the staging step.
    Capturing the data conserves the downstream analysis to be deterministic and 
    independent of external UniProt availability.
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                 INSERT INTO staged_proteins (
                 experiment_id,
                 uniprot_accession,
                 wt_protein_sequence,
                 retrieved_at
                 )
                VALUES (
                 :eid,
                 :acc,
                 :seq,
                 CURRENT_TIMESTAMP()
                 )
                ON CONFLICT (experiment_id) DO UPDATE SET
                 uniprot_accession = EXCLUDED.uniprot_accession,
                 wt_protein_sequence = EXCLUDED.wt_protein_sequence,
                 retrieved_at = EXCLUDED.retrieved_at
            """),
            {"eid": experiment_id, "acc": uniprot_accession, "seq": wt_protein_sequence},
        )

         
def get_staged_wt_protein(
        engine: Engine,
        experiment_id: int,
) -> Tuple[str, str]:
    """
    Obtains the staged UniProt accession and WT protein sequence.

    Utilised for validation or inspection prior to analysis execution.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                 SELECT uniprot_accession, wt_protein_sequence
                 FROM  staged_proteins
                 WHERE experiment_id = :eid
                 """),
            {"eid": experiment_id},
        ).fetchone()

    if not row:
        raise ValueError(
            f"No staged WT protein found for experiment_id={experiment_id}"
        )
    return str(row[0]), str(row[1])

# Analysis reference loading
def get_wt_reference(engine: Engine, experiment_id: int) -> Tuple[str, str]:
    """
    Load the WT protein (from staged Uniprot retrieval) and WT plasmid DNA for 
    sequence analysis.
    """
    with engine.connect() as conn:
        wt_protein = conn.execute(
            text("""
                 SELECT wt_protein_sequence
                 FROM staged_proteins 
                 WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).scalar_one()
        
        wt_plasmid_dna = conn.execute(
            text("""
                SELECT wt_plasmid_dna
                FROM plasmids 
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).scalar_one()

    return str(wt_protein), str(wt_plasmid_dna)

def load_wt_mapping(engine: Engine, experiment_id: int) -> Optional[WTMapping]:
    """
    Load a previously computed WT gene mapping.

    Returns:
        WTMapping if present, otherwise None
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT 
                    mapping_strand,
                    mapping_frame,
                    cds_start_0based,
                    cds_end_0based_excl,
                    wt_cds_dna,
                    wt_translated_protein,
                    mapping_identity= :identity,
                    validation_status = 'VALID',
                    mapping_alignment_score = :score,
                FROM plasmids
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).mapping().first()

    # No record or mapping not yet computed
    if not row or row["mapping_strand"] is None:
        return None

    return WTMapping(
        strand=row["mapping_strand"],
        frame=int(row["mapping_frame"]),
        cds_start_0based=int(row["cds_start_0based"]),
        cds_end_0based_excl=int(row["cds_end_0based_excl"]),
        wt_cds_dna=row["wt_cds_dna"],
        wt_protein_aa=row["wt_translated_protein"],
        match_identity_pct=float(row["mapping_identity"]),
        alignment_score=float(row["mapping_alignment_score"]),
    )

def list_variants(engine: Engine, experiment_id: int) -> List[Tuple[int, str]]:
    """
    Retrieve all variant plasmid sequences for an experiment.

    Returns only: 
        List of (variant_id, assembled_dna_sequence)
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT variant_id, assembled_dna
                FROM variants
                WHERE experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchall()

    return [(int(r[0]), str(r[1])) for r in rows]

# Write operations

def update_experiment_status(engine: Engine, experiment_id: int, status: str) -> None:
    """
    Update experiment-level analysis status

    Used by the orchestrator to mark: 
    - analysis start 
    - successful completion
    - failure for debugging and UI feedback 
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE experiments
                SET analysis_status = :status
                WHERE experiment_id = :eid
            """),
            {"status": status, "eid": experiment_id},
        )

def save_wt_mapping(engine: Engine, experiment_id: int, mapping: WTMapping) -> None:
    """
    Stores the WT gene mapping results to avoid recomputation for every variant
    this includes:
    - CDS coordinates
    - strand and reading frame
    - translated WT wt_protein
    - identity score.
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE plasmids
                SET 
                    mapping_strand = :strand,
                    mapping_frame = :frame,
                    cds_start_0based = :cds_start,
                    cds_end_0based_excl = :cds_end,
                    wt_cds_dna = :wt_cds,
                    wt_translated_protein = :wt_protein,
                    mapping_identity = :identity,
                    validation_status = 'VALID',
                    mapped_at = CURRENT_TIMESTAMP()
                WHERE experiment_id = :eid
            """),
            {
                "strand": mapping.strand,
                "frame": mapping.frame,
                "cds_start": mapping.cds_start_0based,
                "cds_end": mapping.cds_end_0based_excl,
                "wt_cds": mapping.wt_cds_dna,
                "wt_protein": mapping.wt_protein_aa,
                "identity": mapping.match_identity_pct,
                "eid": experiment_id,
            },
        )

def save_variant_sequence_analysis(
    engine: Engine,
    variant_id: int,
    result: VariantSeqResult,
    counts: MutationCounts,
    ) -> None:
    """
    conserves per-variant sequence analysis results.

    This function is idempotent:
    - can be called multiple times for the same variant_id.
    - overwrites previous results.

    Stored outputs are essential for downstream analysis and reporting for:
    - activity scoring
    - result tables
    - PCA / t-SNE feature extraction
    """
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO sequence_analysis (
                    variant_id,
                    cds_start_0based,
                    cds_end_0based_excl,
                    strand,
                    frame,
                    cds_dna,
                    protein_sequence,
                    has_frameshift,
                    has_premature_stop,
                    has_ambiguous_bases,
                    qc_notes,
                    synonymous_count,
                    nonsynonymous_count,
                    total_mutation_count,
                    analysed_at
                )
                VALUES (
                    :variant_id,
                    :start,
                    :end_excl,
                    :strand,
                    :frame,
                    :cds_dna,
                    :protein,
                    :frameshift,
                    :prem_stop,
                    :ambig,
                    :notes,
                    :syn,
                    :nonsyn,
                    :total,
                    CURRENT_TIMESTAMP
                )
                ON CONFLICT (variant_id) DO UPDATE SET
                    cds_start_0based = EXCLUDED.cds_start_0based,
                    cds_end_0based_excl = EXCLUDED.cds_end_0based_excl,
                    strand = EXCLUDED.strand,
                    frame = EXCLUDED.frame,
                    cds_dna = EXCLUDED.cds_dna,
                    protein_sequence = EXCLUDED.protein_sequence,
                    has_frameshift = EXCLUDED.has_frameshift,
                    has_premature_stop = EXCLUDED.has_premature_stop,
                    has_ambiguous_bases = EXCLUDED.has_ambiguous_bases,
                    qc_notes = EXCLUDED.qc_notes,
                    synonymous_count = EXCLUDED.synonymous_count,
                    nonsynonymous_count = EXCLUDED.nonsynonymous_count,
                    total_mutation_count = EXCLUDED.total_mutation_count,
                    analysed_at = EXCLUDED.analysed_at
            """),
            {
                "variant_id": variant_id,
                "start": result.cds_start_0based,
                "end_excl": result.cds_end_0based_excl,
                "strand": result.strand,
                "frame": result.frame,
                "cds_dna": result.cds_dna,
                "protein": result.protein_sequence,
                "frameshift": result.has_frameshift,
                "prem_stop": result.has_premature_stop,
                "ambig": result.has_ambiguous_bases,
                "notes": result.qc_notes,
                "syn": counts.synonymous,
                "nonsyn": counts.nonsynonymous,
                "total": counts.total,
            },
        ) 

def replace_variant_mutations(
    engine: Engine,
    variant_id: int,
    mutations: Iterable[MutationRecord],
    ) -> None:
    """
    Replaces all mutation records for a given variant.

    Existing mutations are erased before incorporating updated records to prevemt duplication
    after re-analysis.
    """
    mutations = list(mutations)
    if not mutations:
        return

    with engine.begin() as conn:
        # Delete existing mutations
        conn.execute(
            text("""
                DELETE FROM mutations
                WHERE variant_id = :vid
            """),
            {"vid": variant_id},
        )

        # Insert new mutations
        for m in mutations:
            conn.execute(
                text("""
                    INSERT INTO mutations (
                        variant_id,
                        aa_position,
                        wt_aa,
                        var_aa,
                        codon_position,
                        wt_codon,
                        var_codon,
                        mutation_type,
                        note
                    )
                    VALUES (
                        :vid,
                        :aa_pos,
                        :wt_aa,
                        :var_aa,
                        :codon_pos,
                        :wt_codon,
                        :var_codon,
                        :mut_type,
                        :note
                    )
                """),
            [
                {
                    "vid": variant_id,
                    "aa_pos": m.position_1based,
                    "wt_aa": m.wt_aa,
                    "var_aa": m.var_aa,
                    "codon_pos": m.codon_index_1based,
                    "wt_codon": m.wt_codon,
                    "var_codon": m.var_codon,
                    "mut_type": m.mutation_type,
                    "note": m.note,
                }
                for m in mutations
            ],
            )