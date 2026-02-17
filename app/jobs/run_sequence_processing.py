"""
Sequence processing orchestrator for variant analysis pipeline.

This module provides the main entry point for processing all variants in an
experiment. It coordinates the workflow: WT mapping, variant CDS extraction,
mutation calling, and result persistence.

Pipeline Architecture:
    1. Load WT References: Obtains the UniProt protein and WT plasmid DNA
    2. WT Mapping (cached): Computes or loads 6-frame gene mapping
    3. Variant Processing Loop:
        a. Extracts the variant CDS using WT coordinates
        b. Translates and performs QC checks
        c. Calls mutations against WT (codon-by-codon or alignment-based)
        d. Persists results and mutation records
    4. Status Tracking: Updates experiment status (ANALYSED, FAILED, etc.)

Error Recovery:
    - Individual variant failures are logged but don't affect processing
    - Failed variants get QC-only records with error details in notes
    - Final status reflects whether any variants failed (ANALYSED_WITH_ERRORS)

Command-Line Usage:
    python -m app.jobs.run_sequence_processing <experiment_id>

Integration Points:
    - Called by Flask job queue for web UI workflows
    - Can be invoked directly for testing or batch processing
    - All database writes are atomic (per-variant transactions)

Note:
    WT mapping is cached after first computation to avoid expensive recomputation
    for every variant. Cache invalidation requires manual database update.
"""

from __future__ import annotations

import sys
import logging
from typing import Iterable, Tuple, List

from app.config import settings
from app.services import db_repo
from app.services.db_repo import get_engine
from app.services.sequence_service import (
    map_wt_gene_in_plasmid,
    process_variant_plasmid,
    call_mutations_against_wt,
    MutationCounts,
    MutationRecord
)

logger = logging.getLogger(__name__)


def _empty_counts() -> MutationCounts:
    """
    Returns zero mutation counts for failed or non-processable variants.
    
    Checks if settings provides a cached EMPTY_MUTATION_COUNTS for performance
    optimisation, otherwise constructs a new instance.
    
    Returns:
        MutationCounts: All-zero counts (synonymous=0, nonsynonymous=0, total=0).
    """
    empty = getattr(settings, "EMPTY_MUTATION_COUNTS", None)
    if isinstance(empty, MutationCounts):
        return empty
    return MutationCounts(synonymous=0, nonsynonymous=0, total=0)


def run_sequence_processing(experiment_id: int) -> None:
    """
    Execute complete sequence processing pipeline for one experiment.
    
    Processes all variants in the experiment sequentially, performing CDS
    extraction, translation, QC checks, and mutation calling. Results are
    persisted to the database with atomic per-variant transactions.
    
    Workflow:
        1. Update status to "ANALYSIS_RUNNING"
        2. Load WT protein and plasmid DNA references
        3. Compute or load cached WT gene mapping (6-frame search)
        4. For each variant:
            - Extracts the variant CDS using WT coordinates
            - Translates to protein
            - Runs QC checks (frameshifts, stop codons, ambiguous bases)
            - Calls mutations (strategy adapts to sequence characteristics)
            - Saves results and mutation records
        5. Updates final status (ANALYSED, ANALYSED_WITH_ERRORS, or FAILED)
    
    Error Handling:
        - Individual variant errors: Logged, QC-only record saved, processing continues
        - Fatal errors (WT mapping, DB connection): Status set to FAILED, exception raised
    
    Args:
        experiment_id: Unique experiment identifier (must be positive integer).
    
    Raises:
        ValueError: If experiment_id <= 0.
        Exception: If fatal error occurs during WT reference loading or mapping.
    
    Database Effects:
        - Updates experiments.analysis_status (ANALYSIS_RUNNING → final state)
        - Inserts/updates wt_mappings (if not cached)
        - Inserts/updates sequence_analysis per variant
        - Replaces mutations per variant (atomic delete + insert)
    
    Note:
        Progress is logged every LOG_EVERY_N variants (configurable via settings).
        The function is idempotent - safe to re-run on the same experiment_id.
    """
    if experiment_id <= 0:
        raise ValueError("experiment_id must be a positive integer.")
    
    engine = get_engine()

    logger.info(
        "Starting sequence processing for experiment %s",
        experiment_id,
    )

    db_repo.update_experiment_status(engine, experiment_id, "ANALYSIS_RUNNING")

    had_variant_errors = False

    try:
        # Load WT References
        wt_protein_aa, wt_plasmid_dna = db_repo.get_wt_reference(
            engine, experiment_id
        )

        # Compute or Load Cached WT Mapping (expensive operation)
        wt_mapping = db_repo.load_wt_mapping(engine, experiment_id)
        if wt_mapping is None:
            logger.info("Computing WT gene mapping (6-frame search)...")
            wt_mapping = map_wt_gene_in_plasmid(wt_protein_aa, wt_plasmid_dna)
            db_repo.save_wt_mapping(engine, experiment_id, wt_mapping)
            logger.info(
                "WT mapping cached: strand=%s, frame=%d, identity=%.2f%%",
                wt_mapping.strand,
                wt_mapping.frame,
                wt_mapping.match_identity_pct,
            )
        # Load All Variants for Processing
        variants: List[Tuple[int, str]] = sorted(
            db_repo.list_variants(engine, experiment_id), 
            key=lambda x: x[0],
        )
        
        total_variants = len(variants)
        logger.info("Processing %d variants for experiment %s", total_variants, experiment_id)

        log_every_n = max(1, int(getattr(settings, "LOG_EVERY_N", 50)))

        # Process Each Variant
        for idx, (variant_id, variant_plasmid_dna) in enumerate(variants, start=1):
            try:
                seq_result = process_variant_plasmid(
                    variant_plasmid_dna, 
                    wt_mapping,
                    fallback_search=settings.FALLBACK_SEARCH,
                )
                
                if not seq_result.cds_dna:
                    db_repo.save_variant_sequence_analysis(
                        engine,
                        variant_id,
                        seq_result,
                        counts=_empty_counts()
                    )
                    db_repo.replace_variant_mutations(engine, variant_id, [])
                else:
                    mutations, counts = call_mutations_against_wt(
                        wt_mapping.wt_cds_dna,
                        seq_result.cds_dna,
                    )

                    db_repo.save_variant_sequence_analysis(engine, variant_id, seq_result, counts)
                    db_repo.replace_variant_mutations(engine, variant_id, mutations)

            except Exception as e:
                # Catch variant-specific errors, log, and continue processing
                had_variant_errors = True

                # Create QC-only record with error details
                from app.services.sequence_service import QCFlags, VariantSeqResult 

                qc_only = VariantSeqResult(
                    cds_start_0based=wt_mapping.cds_start_0based,
                    cds_end_0based_excl=wt_mapping.cds_end_0based_excl,
                    strand=wt_mapping.strand,
                    frame=wt_mapping.frame,
                    cds_dna=None,
                    protein_aa=None,
                    qc=QCFlags(
                        has_frameshift=False,
                        has_premature_stop=False,
                        has_ambiguous_bases=False,
                        notes=f"Variant processing failed: {type(e).__name__}: {e}"
                    ),
                )   
                db_repo.save_variant_sequence_analysis(engine, variant_id, qc_only, counts=_empty_counts())
                db_repo.replace_variant_mutations(engine, variant_id, [])

                logger.exception(
                    "Error processing variant %d in experiment %s. Recorded QC-only result.",
                    variant_id,
                    experiment_id,
                )
 
            # Progress logging
            if idx % log_every_n == 0 or idx == total_variants:
                logger.info(
                    "Processed %d/%d variants (experiment %s)",
                    idx, 
                    total_variants,
                    experiment_id,
                )
        
        # ====================================================================
        # Update Final Status
        # ====================================================================
        final_status = "ANALYSED_WITH_ERRORS" if had_variant_errors else "ANALYSED"
        db_repo.update_experiment_status(engine, experiment_id, final_status)

        logger.info(
            "Sequence processing completed for experiment %s (status=%s)",
            experiment_id,
            final_status,
        )

    except Exception:
        # Fatal error: update status and re-raise
        db_repo.update_experiment_status(engine, experiment_id, "FAILED")

        logger.exception(
            "Sequence processing failed for experiment %s",
            experiment_id,
        )
        raise


# ============================================================================
# Command-Line Interface
# ============================================================================

if __name__ == "__main__":
    """
    CLI entry point for direct execution.
    
    Usage:
        python -m app.jobs.run_sequence_processing <experiment_id>
    
    This enables testing and batch processing outside the Flask web application
    or job queue (e.g., Celery, RQ).
    
    Example:
        python -m app.jobs.run_sequence_processing 42
    """
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.jobs.run_sequence_processing <experiment_id>")
    
    # Configure basic logging for CLI usage
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    run_sequence_processing(int(sys.argv[1]))
    
