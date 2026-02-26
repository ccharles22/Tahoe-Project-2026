"""
Sequence processing orchestrator for variant analysis pipeline.

Coordinates WT mapping, variant processing, mutation calling, and DB
persistence for an experiment. See the project MkDocs for pipeline
architecture details.

Usage:
    python -m app.jobs.run_sequence_processing <experiment_id>
"""

from __future__ import annotations

import sys
import logging
import threading
from typing import Tuple, List

from app.config import settings
from app.services.sequence import db_repo
from app.services.sequence.db_repo import get_engine, VariantAnalysisItem
from app.services.sequence.sequence_service import (
    map_wt_gene_in_plasmid,
    process_variant_plasmid,
    call_mutations_against_wt,
    MutationCounts,
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


def run_sequence_processing(experiment_id: int, *, force_reprocess: bool = False) -> None:
    """
    Run the full variant-analysis pipeline for one experiment.

    See the project MkDocs (Architecture / Visualisations) for the
    detailed workflow, error-handling strategy, and database effects.

    Args:
        experiment_id: Positive integer identifying the experiment.
        force_reprocess: Re-process variants that already have results.

    Raises:
        ValueError: If experiment_id <= 0.
        Exception: On fatal errors (WT loading, DB connection).
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
        wt_protein_aa, wt_plasmid_dna = db_repo.get_wt_reference(
            engine, experiment_id
        )
        user_id, _ = db_repo.get_experiment_user_and_wt(engine, experiment_id)

        wt_mapping = db_repo.load_wt_mapping(engine, experiment_id, user_id)
        if wt_mapping is None:
            logger.info("Computing WT gene mapping (6-frame search)...")
            wt_mapping = map_wt_gene_in_plasmid(wt_protein_aa, wt_plasmid_dna)
            db_repo.upsert_wt_mapping(engine, experiment_id, user_id, wt_mapping)
            logger.info(
                "WT mapping cached: strand=%s, frame=%d, identity=%.2f%%",
                wt_mapping.strand,
                wt_mapping.frame,
                wt_mapping.match_identity_pct,
            )
        variants: List[Tuple[int, str]] = sorted(
            db_repo.list_variants_by_experiment(engine, experiment_id), 
            key=lambda x: x[0],
        )

        # Skip already-processed variants unless forced
        if not force_reprocess:
            already_done = db_repo.list_processed_variant_ids(engine, experiment_id)
            if already_done:
                before = len(variants)
                variants = [(vid, dna) for vid, dna in variants if vid not in already_done]
                skipped = before - len(variants)
                logger.info(
                    "Skipping %d already-processed variants (use force_reprocess=True to override)",
                    skipped,
                )
        
        total_variants = len(variants)
        logger.info("Processing %d variants for experiment %s", total_variants, experiment_id)

        log_every_n = max(1, int(getattr(settings, "LOG_EVERY_N", 50)))
        batch_size = max(1, int(getattr(settings, "DB_BATCH_SIZE", 25)))
        pending: List[VariantAnalysisItem] = []

        def _flush_batch() -> None:
            """Persist accumulated items in one transaction."""
            if not pending:
                return
            db_repo.insert_variant_analyses_batch(
                engine,
                experiment_id=experiment_id,
                user_id=user_id,
                items=list(pending),
            )
            pending.clear()

        for idx, (variant_id, variant_plasmid_dna) in enumerate(variants, start=1):
            try:
                seq_result = process_variant_plasmid(
                    variant_plasmid_dna, 
                    wt_mapping,
                    fallback_search=settings.FALLBACK_SEARCH,
                )
                
                # Flag QC-level failures that don't raise exceptions
                if (
                    not seq_result.cds_dna
                    or seq_result.protein_aa is None
                    or seq_result.qc.has_frameshift
                    or seq_result.qc.has_premature_stop
                ):
                    had_variant_errors = True
                    if not seq_result.cds_dna:
                        logger.warning(
                            "Variant %d: no CDS extracted (experiment %s)",
                            variant_id, experiment_id,
                        )
                    elif seq_result.protein_aa is None:
                        logger.warning(
                            "Variant %d: translation failed (experiment %s)",
                            variant_id, experiment_id,
                        )

                if not seq_result.cds_dna:
                    pending.append(VariantAnalysisItem(
                        variant_id=variant_id,
                        result=seq_result,
                        counts=_empty_counts(),
                        mutations=[],
                    ))
                else:
                    mutations, counts = call_mutations_against_wt(
                        wt_mapping.wt_cds_dna,
                        seq_result.cds_dna,
                    )

                    pending.append(VariantAnalysisItem(
                        variant_id=variant_id,
                        result=seq_result,
                        counts=counts,
                        mutations=list(mutations),
                    ))

            except Exception as e:
                had_variant_errors = True

                from app.services.sequence.sequence_service import QCFlags, VariantSeqResult 

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
                pending.append(VariantAnalysisItem(
                    variant_id=variant_id,
                    result=qc_only,
                    counts=_empty_counts(),
                    mutations=[],
                ))

                logger.exception(
                    "Error processing variant %d in experiment %s. Recorded QC-only result.",
                    variant_id,
                    experiment_id,
                )

            # Flush batch when it reaches the configured size
            if len(pending) >= batch_size:
                _flush_batch()

            if idx % log_every_n == 0 or idx == total_variants:
                logger.info(
                    "Processed %d/%d variants (experiment %s)",
                    idx, 
                    total_variants,
                    experiment_id,
                )

        # Flush any remaining items
        _flush_batch()
        
        final_status = "ANALYSED_WITH_ERRORS" if had_variant_errors else "ANALYSED"
        db_repo.update_experiment_status(engine, experiment_id, final_status)

        logger.info(
            "Sequence processing completed for experiment %s (status=%s)",
            experiment_id,
            final_status,
        )

    except Exception:
        logger.exception(
            "Sequence processing failed for experiment %s",
            experiment_id,
        )
        try:
            db_repo.update_experiment_status(engine, experiment_id, "FAILED")
        except Exception:
            logger.exception(
                "Could not update status to FAILED for experiment %s",
                experiment_id,
            )
        raise


def submit_sequence_processing(
    experiment_id: int, *, force_reprocess: bool = False
) -> threading.Thread:
    """
    Launches run_sequence_processing in a background daemon thread.

    Call this from a Flask route instead of run_sequence_processing()
    so the HTTP response returns immediately while the pipeline runs
    in the background.  The experiment's analysis_status column tracks
    progress (ANALYSIS_RUNNING → ANALYSED / FAILED).

    Args:
        experiment_id: Experiment to process.
        force_reprocess: If True, re-process all variants even if
            they already have results.

    Returns the Thread object for optional monitoring.
    """
    t = threading.Thread(
        target=run_sequence_processing,
        args=(experiment_id,),
        kwargs={"force_reprocess": force_reprocess},
        name=f"seq-processing-{experiment_id}",
        daemon=True,
    )
    t.start()
    logger.info("Submitted experiment %s for background processing (thread=%s)", experiment_id, t.name)
    return t


# ============================================================================
# Command-Line Interface
# ============================================================================

if __name__ == "__main__":
    # CLI entry point: python -m app.jobs.run_sequence_processing <experiment_id>
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.jobs.run_sequence_processing <experiment_id>")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    run_sequence_processing(int(sys.argv[1]))
    
