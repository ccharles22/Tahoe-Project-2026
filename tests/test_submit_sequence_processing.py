"""
Tests for submit_sequence_processing() background thread behaviour.

All database and sequence-service calls are mocked so these tests
run locally without a PostgreSQL connection.

Usage:
    python -m pytest tests/test_submit_sequence_processing.py -v
"""
from __future__ import annotations

import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from app.services.sequence.sequence_service import (
    MutationCounts,
    MutationRecord,
    QCFlags,
    VariantSeqResult,
    WTMapping,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FAKE_EXPERIMENT_ID = 42

FAKE_WT_MAPPING = WTMapping(
    strand="PLUS",
    frame=0,
    cds_start_0based=100,
    cds_end_0based_excl=400,
    wt_cds_dna="ATG" + "GCT" * 99,
    wt_protein_aa="M" + "A" * 99,
    match_identity_pct=100.0,
    alignment_score=500.0,
)

FAKE_SEQ_RESULT = VariantSeqResult(
    cds_start_0based=100,
    cds_end_0based_excl=400,
    strand="PLUS",
    frame=0,
    cds_dna="ATG" + "GCT" * 99,
    protein_aa="M" + "A" * 99,
    qc=QCFlags(
        has_ambiguous_bases=False,
        has_frameshift=False,
        has_premature_stop=False,
    ),
)

FAKE_COUNTS = MutationCounts(synonymous=1, nonsynonymous=0, total=1)

FAKE_MUTATION = MutationRecord(
    mutation_type="SYNONYMOUS",
    codon_index_1based=5,
    aa_position_1based=5,
    wt_codon="GCT",
    var_codon="GCC",
    wt_aa="A",
    var_aa="A",
)

# Two fake variants
FAKE_VARIANTS = [(1, "ATGAAA"), (2, "ATGCCC")]


def _patch_pipeline():
    """Return a dict of patch objects for all external dependencies."""
    return {
        "get_engine": patch(
            "app.jobs.run_sequence_processing.get_engine",
            return_value=MagicMock(name="engine"),
        ),
        "update_status": patch(
            "app.jobs.run_sequence_processing.db_repo.update_experiment_status",
        ),
        "get_wt_ref": patch(
            "app.jobs.run_sequence_processing.db_repo.get_wt_reference",
            return_value=("MAAAA", "ATGAAAA"),
        ),
        "get_user": patch(
            "app.jobs.run_sequence_processing.db_repo.get_experiment_user_and_wt",
            return_value=(7, None),
        ),
        "load_wt_mapping": patch(
            "app.jobs.run_sequence_processing.db_repo.load_wt_mapping",
            return_value=FAKE_WT_MAPPING,
        ),
        "list_variants": patch(
            "app.jobs.run_sequence_processing.db_repo.list_variants_by_experiment",
            return_value=FAKE_VARIANTS,
        ),
        "process_variant": patch(
            "app.jobs.run_sequence_processing.process_variant_plasmid",
            return_value=FAKE_SEQ_RESULT,
        ),
        "call_mutations": patch(
            "app.jobs.run_sequence_processing.call_mutations_against_wt",
            return_value=([FAKE_MUTATION], FAKE_COUNTS),
        ),
        "batch_insert": patch(
            "app.jobs.run_sequence_processing.db_repo.insert_variant_analyses_batch",
        ),
        "list_processed": patch(
            "app.jobs.run_sequence_processing.db_repo.list_processed_variant_ids",
            return_value=set(),  # no variants already processed
        ),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSubmitSequenceProcessing:
    """Verifies the background-thread wrapper."""

    def test_returns_immediately(self):
        """submit_sequence_processing() must return a Thread within milliseconds."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            t0 = time.perf_counter()
            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            elapsed = time.perf_counter() - t0

            # The call should return almost instantly (< 1 s), proving it's
            # non-blocking.  The actual pipeline runs in the background.
            assert elapsed < 1.0, f"submit returned in {elapsed:.2f}s — should be < 1s"
            assert isinstance(thread, threading.Thread)

            # Wait for background work to finish so assertions are valid
            thread.join(timeout=5)
            assert not thread.is_alive(), "Background thread did not finish in time"
        finally:
            for p in patches.values():
                p.stop()

    def test_thread_is_daemon(self):
        """Background thread must be a daemon so it won't block process exit."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            assert thread.daemon is True
            thread.join(timeout=5)
        finally:
            for p in patches.values():
                p.stop()

    def test_thread_name_contains_experiment_id(self):
        """Thread name should include the experiment ID for debugging."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            assert str(FAKE_EXPERIMENT_ID) in thread.name
            thread.join(timeout=5)
        finally:
            for p in patches.values():
                p.stop()

    def test_pipeline_runs_to_completion(self):
        """The background thread should execute the full pipeline."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            thread.join(timeout=10)

            # Status updated to ANALYSIS_RUNNING at start
            status_calls = mocks["update_status"].call_args_list
            assert len(status_calls) >= 2, "Expected at least 2 status updates (start + end)"
            assert status_calls[0].args[2] == "ANALYSIS_RUNNING"
            # Final status should be ANALYSED (no errors in our mocks)
            assert status_calls[-1].args[2] == "ANALYSED"

            # Batch insert called at least once (for our 2 fake variants)
            assert mocks["batch_insert"].called
        finally:
            for p in patches.values():
                p.stop()

    def test_pipeline_sets_failed_on_fatal_error(self):
        """If the pipeline raises, status should be set to FAILED."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        # Make WT reference loading explode
        mocks["get_wt_ref"].side_effect = RuntimeError("DB connection lost")

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            thread.join(timeout=5)

            status_calls = mocks["update_status"].call_args_list
            final_status = status_calls[-1].args[2]
            assert final_status == "FAILED", f"Expected FAILED, got {final_status}"
        finally:
            for p in patches.values():
                p.stop()

    def test_variant_error_does_not_crash_pipeline(self):
        """A single variant failure should not stop other variants."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        # First call raises, second succeeds
        mocks["process_variant"].side_effect = [
            RuntimeError("bad sequence"),
            FAKE_SEQ_RESULT,
        ]

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            thread.join(timeout=10)

            status_calls = mocks["update_status"].call_args_list
            final_status = status_calls[-1].args[2]
            # Should complete with errors, not crash
            assert final_status == "ANALYSED_WITH_ERRORS"

            # Batch insert should still have been called
            assert mocks["batch_insert"].called
        finally:
            for p in patches.values():
                p.stop()

    def test_multiple_concurrent_submissions(self):
        """Multiple experiments can be submitted concurrently."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            threads = [submit_sequence_processing(i) for i in range(1, 4)]

            for t in threads:
                t.join(timeout=10)
                assert not t.is_alive()

            # Each experiment should have triggered status updates
            assert mocks["update_status"].call_count >= 6  # 2 per experiment × 3
        finally:
            for p in patches.values():
                p.stop()


class TestRunSequenceProcessingDirect:
    """Verifies run_sequence_processing() itself (called synchronously)."""

    def test_rejects_invalid_experiment_id(self):
        """experiment_id <= 0 should raise ValueError."""
        from app.jobs.run_sequence_processing import run_sequence_processing

        with pytest.raises(ValueError, match="positive integer"):
            run_sequence_processing(0)

        with pytest.raises(ValueError, match="positive integer"):
            run_sequence_processing(-1)
