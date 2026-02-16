from __future__ import annotations

import sys
import logging

from app.config import settings
from app.services.sequence import db_repo
from app.services.sequence.db_repo import get_engine
from app.services.sequence.sequence_service import (
    map_wt_gene_in_plasmid,
    process_variant_plasmid,
    call_mutations_against_wt,
)

# Module-level logger (uses central logging configuration)
logger = logging.getLogger(__name__)

def run_sequence_processing(experiment_id: int) -> None:
    """
    Performs sequence processing for a single experiment.

    Pipeline stages:
    - Load WT references (UniProt WT protein + WT plasmid DNA)
    - Ensure WT gene mapping exists (cached in DB)
    - Process each variant deterministically (CDS extraction -> translation -> QC)
    - Save all analysis outputs onto PostgreSQL
    """
    engine = get_engine()

    logger.info(
        "Starting sequence processing for experiment %s",
        experiment_id,
    )

    # Mark experiment as running so UI can display the progress
    db_repo.update_experiment_status(engine, experiment_id, "ANALYSIS_RUNNING")

    try:
        # Load WT references required for mapping and mutation calling
        wt_protein_aa, wt_plasmid_dna = db_repo.get_wt_reference(
            engine, experiment_id
        )

        # WT gene mapping is an expensive step; compute once per experiment
        wt_mapping = db_repo.load_wt_mapping(engine,experiment_id)
        if wt_mapping is None:
            wt_mapping = map_wt_gene_in_plasmid(
                wt_protein_aa, wt_plasmid_dna
            )
            db_repo.save_wt_mapping(engine, experiment_id, wt_mapping)

        # Variant processing loop
        variants = sorted(db_repo.list_variants(engine, experiment_id), 
                          key=lambda x: x[0],)
        total_variants = len(variants)

        logger.info(
            "Processing%d variants for experiment %s",
            total_variants,
            experiment_id,
        )

        log_every_n = settings.LOG_EVERY_N

        for idx, (variant_id, variant_plasmid_dna) in enumerate(variants, start=1):                                                    
            # Extract CDS, translate to protein, and genereate QC flags 
            seq_result = process_variant_plasmid(
                variant_plasmid_dna, 
                wt_mapping,
                fallback_search=settings.FALLBACK_SEARCH,
            )

            # If CDS extraction/translation failed, store QC-only output and skip mutation calling.
            if not seq_result.cds_dna:
                db_repo.save_variant_sequence_analysis(
                    engine,
                    variant_id,
                    seq_result,
                    counts=settings.EMPTY_MUTATION_COUNTS, 
                )
                if idx % log_every_n == 0 or idx == total_variants:
                    logger.info("Processed %d/%d variants (experiment %s)", idx,
                                total_variants, experiment_id)
                    continue


            # Identify and classify mutations vs WT
            mutations, counts = call_mutations_against_wt(
                wt_mapping.wt_cds_dna,
                seq_result.cds_dna,
            )

            # Persist per-variant outputs required for reporting
            db_repo.save_variant_sequence_analysis(
                engine, variant_id, seq_result, counts
            )
            db_repo.replace_variant_mutations(
                engine, variant_id, mutations
            )

            # Periodic progress logging 
            if idx % log_every_n == 0 or idx == total_variants:
                logger.info(
                    "Processed %d/%d variants (experiment %s)",
                    idx, 
                    total_variants,
                    experiment_id,
                )
        # Mark successful completion
        db_repo.update_experiment_status(engine, experiment_id, "ANALYSED")

        logger.info(
            "Sequence processing completed successfully for experiment %s",
            experiment_id,
        )

    except Exception:
        # Failure is recorded for debugging and UI feedback, then re-raised
        db_repo.update_experiment_status(engine, experiment_id, "FAILED")

        logger.exception(
            "Sequence processing failed for experiment %s",
            experiment_id,
        )
        raise

# Command Line Interface entry point

if __name__ == "__main__":
    """
    Authorises the job to be conducted directly from the command line:

        python -m app.jobs.run_sequence_processing <experiment_id>

    This is beneficial for testing and batch execution outside Flask.
    """
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.jobs.run_sequence_processing <experiment_id>")
    run_sequence_processing(int(sys.argv[1]))
    
