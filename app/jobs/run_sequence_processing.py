"""
Sequence processing orchestrator for variant analysis pipeline.

Coordinates WT mapping, variant processing, mutation calling, and DB
persistence for an experiment. See the project MkDocs for pipeline
architecture details.

Usage:
    python -m app.jobs.run_sequence_processing <experiment_id>
"""

from __future__ import annotations

import os
import sys
import logging
import threading
from typing import Tuple, List, Optional

from app.config import settings
from app.services.sequence import db_repo
from app.services.sequence.db_repo import get_engine, VariantAnalysisItem
from app.services.sequence.sequence_service import (
    map_wt_gene_in_plasmid,
    process_variant_plasmid,
    call_mutations_against_wt,
    normalise_dna,
    MutationCounts,
    QCFlags,
    VariantSeqResult,
    WTMapping,
    MutationRecord,
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


def _process_one_variant(
    variant_id: int,
    variant_plasmid_dna: str,
    wt_mapping: WTMapping,
    fallback_search: bool,
    wt_plasmid: Optional[str] = None,
) -> VariantAnalysisItem:
    """Process a single variant — safe for parallel execution via ThreadPoolExecutor."""
    seq_result = process_variant_plasmid(
        variant_plasmid_dna,
        wt_mapping,
        fallback_search=fallback_search,
        wt_plasmid=wt_plasmid,
    )
    if not seq_result.cds_dna:
        return VariantAnalysisItem(
            variant_id=variant_id,
            result=seq_result,
            counts=_empty_counts(),
            mutations=[],
        )
    mutations, counts = call_mutations_against_wt(
        wt_mapping.wt_cds_dna,
        seq_result.cds_dna,
    )
    return VariantAnalysisItem(
        variant_id=variant_id,
        result=seq_result,
        counts=counts,
        mutations=list(mutations),
    )


def _apply_mutation_sanity_guard(
    item: VariantAnalysisItem,
    wt_mapping: WTMapping,
) -> VariantAnalysisItem:
    """
    Suppress biologically implausible mutation profiles from persistence.

    This guard catches the known failure mode where a badly mapped short protein
    is paired with an unrealistically large mutation count.
    """
    protein = item.result.protein_aa
    if not protein:
        return item

    total_mutations = int(item.counts.total or 0)
    protein_len = len(protein)
    wt_len = len(wt_mapping.wt_protein_aa or "")

    short_protein_max_len = int(
        getattr(settings, "MUTATION_SANITY_SHORT_PROTEIN_MAX_LEN", 8)
    )
    short_protein_min_mutations = int(
        getattr(settings, "MUTATION_SANITY_SHORT_PROTEIN_MIN_MUTATIONS", 100)
    )
    severe_ratio_threshold = float(
        getattr(settings, "MUTATION_SANITY_WT_RATIO_THRESHOLD", 0.75)
    )
    severe_ratio_min_len = int(
        getattr(settings, "MUTATION_SANITY_RATIO_MIN_PROTEIN_LEN", 30)
    )
    absolute_max = int(
        getattr(settings, "MUTATION_SANITY_ABSOLUTE_MAX", 150)
    )
    wt_fraction_max = float(
        getattr(settings, "MUTATION_SANITY_WT_FRACTION_MAX", 0.20)
    )

    suspicious_short = (
        protein_len <= short_protein_max_len
        and total_mutations >= short_protein_min_mutations
    )
    suspicious_ratio = (
        wt_len > 0
        and protein_len <= max(severe_ratio_min_len, int(0.10 * wt_len))
        and total_mutations >= int(wt_len * severe_ratio_threshold)
    )
    outlier_threshold = max(absolute_max, int(wt_len * wt_fraction_max)) if wt_len > 0 else absolute_max
    suspicious_outlier = total_mutations > outlier_threshold

    if not (suspicious_short or suspicious_ratio or suspicious_outlier):
        return item

    note = (
        "Mutation sanity guard: implausible mutation profile detected "
        f"(protein_len={protein_len}, total_mutations={total_mutations}, wt_len={wt_len}, "
        f"outlier_threshold={outlier_threshold}). "
        "Marked as failed to avoid contaminating mutation-level summaries."
    )
    existing_note = item.result.qc.notes or ""
    qc_note = f"{existing_note} {note}".strip()

    guarded_result = VariantSeqResult(
        cds_start_0based=item.result.cds_start_0based,
        cds_end_0based_excl=item.result.cds_end_0based_excl,
        strand=item.result.strand,
        frame=item.result.frame,
        cds_dna=item.result.cds_dna,
        protein_aa=None,
        qc=QCFlags(
            has_ambiguous_bases=item.result.qc.has_ambiguous_bases,
            has_frameshift=item.result.qc.has_frameshift,
            has_premature_stop=item.result.qc.has_premature_stop,
            notes=qc_note,
        ),
    )
    return VariantAnalysisItem(
        variant_id=item.variant_id,
        result=guarded_result,
        counts=_empty_counts(),
        mutations=[],
    )


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

        import time as _time
        t_start = _time.perf_counter()

        batch_size = max(1, int(getattr(settings, "DB_BATCH_SIZE", 25)))
        pending: List[VariantAnalysisItem] = []
        total_flushed = 0

        def _flush_batch(last_idx: int) -> None:
            """Persist accumulated items in one transaction."""
            nonlocal total_flushed
            if not pending:
                return
            db_repo.insert_variant_analyses_batch(
                engine,
                experiment_id=experiment_id,
                user_id=user_id,
                items=list(pending),
                overwrite=force_reprocess,
            )
            total_flushed += len(pending)
            pending.clear()
            logger.info(
                "Persisted %d/%d variants (experiment %s)",
                total_flushed, total_variants, experiment_id,
            )

        # ------------------------------------------------------------------
        # Serial variant processing — Python's GIL prevents CPU-bound
        # parallelism so a tight serial loop is faster than ThreadPoolExecutor
        # overhead (executor creation per chunk, future allocation, GIL contention).
        # ------------------------------------------------------------------
        fallback = settings.FALLBACK_SEARCH
        # Normalise the WT plasmid once so backbone-anchor remap can use it.
        wt_plasmid_norm = normalise_dna(wt_plasmid_dna) if wt_plasmid_dna else None
        for idx, (variant_id, variant_plasmid_dna) in enumerate(variants, 1):
            try:
                item = _process_one_variant(
                    variant_id,
                    variant_plasmid_dna,
                    wt_mapping,
                    fallback,
                    wt_plasmid_norm,
                )
                guarded_item = _apply_mutation_sanity_guard(item, wt_mapping)
                if guarded_item is not item:
                    logger.warning(
                        "Variant %d flagged by mutation sanity guard in experiment %s.",
                        variant_id,
                        experiment_id,
                    )
                item = guarded_item
                if (
                    not item.result.cds_dna
                    or item.result.protein_aa is None
                    or item.result.qc.has_frameshift
                    or item.result.qc.has_premature_stop
                ):
                    had_variant_errors = True
                pending.append(item)
            except Exception as e:
                had_variant_errors = True
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
                        notes=f"Variant processing failed: {type(e).__name__}: {e}",
                    ),
                )
                pending.append(VariantAnalysisItem(
                    variant_id=variant_id,
                    result=qc_only,
                    counts=_empty_counts(),
                    mutations=[],
                ))
                logger.warning(
                    "Variant %d failed: %s (experiment %s)",
                    variant_id, e, experiment_id,
                )

            # Flush when batch is full
            if len(pending) >= batch_size:
                _flush_batch(idx)

        # Flush remaining items
        _flush_batch(total_variants)

        elapsed = _time.perf_counter() - t_start
        logger.info(
            "Variant processing completed: %d variants in %.1fs (%.0f ms/variant, experiment %s)",
            total_variants, elapsed, (elapsed / max(1, total_variants)) * 1000, experiment_id,
        )
        
        final_status = "ANALYSED_WITH_ERRORS" if had_variant_errors else "ANALYSED"
        logger.info(
            "Updating experiment %s status from ANALYSIS_RUNNING to %s",
            experiment_id,
            final_status,
        )
        db_repo.update_experiment_status(engine, experiment_id, final_status)
        logger.info(
            "Experiment %s status update committed",
            experiment_id,
        )

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
    
