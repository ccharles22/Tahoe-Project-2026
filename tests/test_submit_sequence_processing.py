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


    def test_qc_failure_frameshift_sets_analysed_with_errors(self):
        """A variant with has_frameshift=True (no exception) → ANALYSED_WITH_ERRORS."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        frameshift_result = VariantSeqResult(
            cds_start_0based=100,
            cds_end_0based_excl=400,
            strand="PLUS",
            frame=0,
            cds_dna="ATGGCTGC",  # 8 bases — not divisible by 3
            protein_aa="MA",
            qc=QCFlags(
                has_ambiguous_bases=False,
                has_frameshift=True,
                has_premature_stop=False,
            ),
        )
        mocks["process_variant"].return_value = frameshift_result

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            thread.join(timeout=10)

            status_calls = mocks["update_status"].call_args_list
            final_status = status_calls[-1].args[2]
            assert final_status == "ANALYSED_WITH_ERRORS", (
                f"Expected ANALYSED_WITH_ERRORS for frameshift QC, got {final_status}"
            )
        finally:
            for p in patches.values():
                p.stop()

    def test_none_protein_sets_analysed_with_errors(self):
        """A variant with protein_aa=None (no exception) → ANALYSED_WITH_ERRORS."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        no_protein_result = VariantSeqResult(
            cds_start_0based=100,
            cds_end_0based_excl=400,
            strand="PLUS",
            frame=0,
            cds_dna="ATGGCTGCC",
            protein_aa=None,  # Translation failed
            qc=QCFlags(
                has_ambiguous_bases=False,
                has_frameshift=False,
                has_premature_stop=False,
                notes="Translation failed: unexpected error",
            ),
        )
        mocks["process_variant"].return_value = no_protein_result

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            thread.join(timeout=10)

            status_calls = mocks["update_status"].call_args_list
            final_status = status_calls[-1].args[2]
            assert final_status == "ANALYSED_WITH_ERRORS", (
                f"Expected ANALYSED_WITH_ERRORS for None protein, got {final_status}"
            )
        finally:
            for p in patches.values():
                p.stop()

    def test_premature_stop_sets_analysed_with_errors(self):
        """A variant with has_premature_stop=True → ANALYSED_WITH_ERRORS."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        premature_stop_result = VariantSeqResult(
            cds_start_0based=100,
            cds_end_0based_excl=400,
            strand="PLUS",
            frame=0,
            cds_dna="ATG" + "GCT" * 99,
            protein_aa="MA" + "A" * 97,
            qc=QCFlags(
                has_ambiguous_bases=False,
                has_frameshift=False,
                has_premature_stop=True,
                notes="Protein truncated due to in-frame stop codon.",
            ),
        )
        mocks["process_variant"].return_value = premature_stop_result

        try:
            from app.jobs.run_sequence_processing import submit_sequence_processing

            thread = submit_sequence_processing(FAKE_EXPERIMENT_ID)
            thread.join(timeout=10)

            status_calls = mocks["update_status"].call_args_list
            final_status = status_calls[-1].args[2]
            assert final_status == "ANALYSED_WITH_ERRORS", (
                f"Expected ANALYSED_WITH_ERRORS for premature stop, got {final_status}"
            )
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

    def test_force_reprocess_overwrites_existing_results(self):
        """Forced reruns must overwrite old sequence-analysis outputs."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        try:
            from app.jobs.run_sequence_processing import run_sequence_processing

            run_sequence_processing(FAKE_EXPERIMENT_ID, force_reprocess=True)

            mocks["list_processed"].assert_not_called()
            assert mocks["batch_insert"].called
            assert mocks["batch_insert"].call_args.kwargs["overwrite"] is True
        finally:
            for p in patches.values():
                p.stop()

    def test_mutation_sanity_guard_marks_implausible_profiles_failed(self):
        """Short proteins with implausibly huge mutation counts should be suppressed."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        short_protein_result = VariantSeqResult(
            cds_start_0based=100,
            cds_end_0based_excl=118,
            strand="PLUS",
            frame=0,
            cds_dna="ATGGCTGCTGCTGCTGCT",
            protein_aa="MAAAA",
            qc=QCFlags(
                has_ambiguous_bases=False,
                has_frameshift=False,
                has_premature_stop=False,
            ),
        )
        huge_counts = MutationCounts(synonymous=0, nonsynonymous=874, total=874)
        huge_mutation = MutationRecord(
            mutation_type="NONSYNONYMOUS",
            codon_index_1based=1,
            aa_position_1based=1,
            wt_codon="GCT",
            var_codon="GTT",
            wt_aa="A",
            var_aa="V",
        )

        mocks["process_variant"].side_effect = [short_protein_result, FAKE_SEQ_RESULT]
        mocks["call_mutations"].side_effect = [
            ([huge_mutation], huge_counts),
            ([FAKE_MUTATION], FAKE_COUNTS),
        ]

        try:
            from app.jobs.run_sequence_processing import run_sequence_processing

            run_sequence_processing(FAKE_EXPERIMENT_ID, force_reprocess=True)

            status_calls = mocks["update_status"].call_args_list
            assert status_calls[-1].args[2] == "ANALYSED_WITH_ERRORS"

            inserted_items = mocks["batch_insert"].call_args.kwargs["items"]
            assert len(inserted_items) == 2

            guarded = inserted_items[0]
            assert guarded.variant_id == 1
            assert guarded.result.protein_aa is None
            assert guarded.counts.total == 0
            assert guarded.mutations == []
            assert "Mutation sanity guard" in (guarded.result.qc.notes or "")
        finally:
            for p in patches.values():
                p.stop()

    def test_mutation_sanity_guard_filters_hundreds_on_long_proteins(self):
        """Hundreds-level mutation counts should be suppressed even on long proteins."""
        patches = _patch_pipeline()
        mocks = {k: p.start() for k, p in patches.items()}

        long_wt_mapping = WTMapping(
            strand="PLUS",
            frame=0,
            cds_start_0based=100,
            cds_end_0based_excl=2740,
            wt_cds_dna="ATG" + "GCT" * 879,
            wt_protein_aa="M" + "A" * 879,
            match_identity_pct=100.0,
            alignment_score=500.0,
        )
        long_protein_result = VariantSeqResult(
            cds_start_0based=100,
            cds_end_0based_excl=2740,
            strand="PLUS",
            frame=0,
            cds_dna="ATG" + "GCT" * 879,
            protein_aa="M" + "A" * 879,
            qc=QCFlags(
                has_ambiguous_bases=False,
                has_frameshift=False,
                has_premature_stop=False,
            ),
        )
        huge_counts = MutationCounts(synonymous=0, nonsynonymous=615, total=615)
        huge_mutation = MutationRecord(
            mutation_type="NONSYNONYMOUS",
            codon_index_1based=1,
            aa_position_1based=1,
            wt_codon="GCT",
            var_codon="GTT",
            wt_aa="A",
            var_aa="V",
        )

        mocks["load_wt_mapping"].return_value = long_wt_mapping
        mocks["process_variant"].side_effect = [long_protein_result, FAKE_SEQ_RESULT]
        mocks["call_mutations"].side_effect = [
            ([huge_mutation], huge_counts),
            ([FAKE_MUTATION], FAKE_COUNTS),
        ]

        try:
            from app.jobs.run_sequence_processing import run_sequence_processing

            run_sequence_processing(FAKE_EXPERIMENT_ID, force_reprocess=True)

            inserted_items = mocks["batch_insert"].call_args.kwargs["items"]
            assert len(inserted_items) == 2

            guarded = inserted_items[0]
            assert guarded.variant_id == 1
            assert guarded.result.protein_aa is None
            assert guarded.counts.total == 0
            assert guarded.mutations == []
            assert "outlier_threshold=" in (guarded.result.qc.notes or "")
        finally:
            for p in patches.values():
                p.stop()


class TestProcessVariantNonZeroFrame:
    """Verify that non-zero reading frames are handled correctly.

    The frame offset is baked into cds_start_0based / cds_end_0based_excl
    during WT mapping, so process_variant_plasmid must NOT trim again.
    """

    # 30-base plasmid: 1 junk base, then ATG GCT GCC = M A A, then padding
    _PLASMID_FRAME1 = "G" + "ATGGCTGCC" + "T" * 20

    def test_frame_1_extracts_correct_cds(self):
        """With frame=1, CDS extracted from coordinates should be exact — no double trim."""
        from app.services.sequence.sequence_service import process_variant_plasmid
        from unittest.mock import patch

        wt_mapping = WTMapping(
            strand="PLUS",
            frame=1,
            cds_start_0based=1,        # already includes frame offset
            cds_end_0based_excl=10,     # 9 bases = 3 codons
            wt_cds_dna="ATGGCTGCC",
            wt_protein_aa="MAA",
            match_identity_pct=100.0,
            alignment_score=100.0,
        )

        with patch(
            "app.services.sequence.sequence_service._needs_variant_remap",
            return_value=False,
        ):
            result = process_variant_plasmid(
                self._PLASMID_FRAME1,
                wt_mapping,
                fallback_search=False,
            )

        assert result.cds_dna == "ATGGCTGCC"
        assert result.protein_aa is not None
        assert result.protein_aa.startswith("M")
        assert not result.qc.has_frameshift

    def test_frame_2_extracts_correct_cds(self):
        """With frame=2, same logic — coordinates already account for frame."""
        from app.services.sequence.sequence_service import process_variant_plasmid
        from unittest.mock import patch

        # 2 junk bases, then ATG AAA GCC = M K A, then padding
        plasmid = "GG" + "ATGAAAGCC" + "T" * 19

        wt_mapping = WTMapping(
            strand="PLUS",
            frame=2,
            cds_start_0based=2,         # already includes frame offset
            cds_end_0based_excl=11,     # 9 bases = 3 codons
            wt_cds_dna="ATGAAAGCC",
            wt_protein_aa="MKA",
            match_identity_pct=100.0,
            alignment_score=100.0,
        )

        with patch(
            "app.services.sequence.sequence_service._needs_variant_remap",
            return_value=False,
        ):
            result = process_variant_plasmid(
                plasmid,
                wt_mapping,
                fallback_search=False,
            )

        assert result.cds_dna == "ATGAAAGCC"
        assert result.protein_aa is not None
        assert not result.qc.has_frameshift
        assert result.frame == 2


class TestCallMutationsIndels:
    """Tests for insertion / deletion calling via protein alignment."""

    def test_insertion_detected(self):
        """A 3-base in-frame insertion should be detected as an INSERTION."""
        from app.services.sequence.sequence_service import call_mutations_against_wt

        # WT:  ATG GCT GCC = M A A (9 bases)
        # Var: ATG GCT AAA GCC = M A K A (12 bases — 3 bp insertion)
        wt_cds = "ATGGCTGCC"
        var_cds = "ATGGCTAAAGCC"

        mutations, counts = call_mutations_against_wt(wt_cds, var_cds)

        # Should route to indel alignment path (lengths differ)
        assert counts.total >= 1
        mutation_types = [m.mutation_type for m in mutations]
        assert any(
            t in ("INSERTION", "NONSYNONYMOUS") for t in mutation_types
        ), f"Expected insertion or substitution, got {mutation_types}"

    def test_deletion_detected(self):
        """A 3-base in-frame deletion should be detected as a DELETION."""
        from app.services.sequence.sequence_service import call_mutations_against_wt

        # WT:  ATG GCT AAA GCC = M A K A (12 bases)
        # Var: ATG GCT GCC = M A A (9 bases — 3 bp deletion)
        wt_cds = "ATGGCTAAAGCC"
        var_cds = "ATGGCTGCC"

        mutations, counts = call_mutations_against_wt(wt_cds, var_cds)

        assert counts.total >= 1
        mutation_types = [m.mutation_type for m in mutations]
        assert any(
            t in ("DELETION", "NONSYNONYMOUS") for t in mutation_types
        ), f"Expected deletion or substitution, got {mutation_types}"

    def test_frameshift_returns_frameshift_record(self):
        """If CDS length is not divisible by 3, should return FRAMESHIFT."""
        from app.services.sequence.sequence_service import call_mutations_against_wt

        wt_cds = "ATGGCTGCC"        # 9 bases (OK)
        var_cds = "ATGGCTGC"         # 8 bases (not divisible by 3)

        mutations, counts = call_mutations_against_wt(wt_cds, var_cds)

        assert len(mutations) == 1
        assert mutations[0].mutation_type == "FRAMESHIFT"
        assert counts.total == 1

    def test_indel_path_preserves_synonymous_codon_events(self):
        """Indel-aware calling should still count synonymous codon substitutions."""
        from app.services.sequence.sequence_service import call_mutations_against_wt

        # WT:  ATG GAA TTT GCT = M E F A
        # Var: ATG GAG AAA TTC GCT = M E K F A
        # Events:
        #   - GAA -> GAG (synonymous E)
        #   - AAA insertion (K)
        #   - TTT -> TTC (synonymous F)
        wt_cds = "ATGGAATTTGCT"
        var_cds = "ATGGAGAAATTCGCT"

        mutations, counts = call_mutations_against_wt(wt_cds, var_cds)

        mutation_types = [m.mutation_type for m in mutations]
        assert counts.total == 3, mutation_types
        assert counts.synonymous == 2, mutation_types
        assert counts.nonsynonymous == 1, mutation_types
        assert mutation_types.count("SYNONYMOUS") == 2, mutation_types
        assert "INSERTION" in mutation_types, mutation_types

    def test_multi_codon_insertion_counts_each_inserted_codon(self):
        """A multi-codon insertion should count one event per inserted codon."""
        from app.services.sequence.sequence_service import call_mutations_against_wt

        # WT:  ATG GCT GCC = M A A
        # Var: ATG AAA TTT GCT GCC = M K F A A
        wt_cds = "ATGGCTGCC"
        var_cds = "ATGAAATTTGCTGCC"

        mutations, counts = call_mutations_against_wt(wt_cds, var_cds)

        mutation_types = [m.mutation_type for m in mutations]
        assert counts.total == 2, mutation_types
        assert counts.synonymous == 0, mutation_types
        assert counts.nonsynonymous == 2, mutation_types
        assert mutation_types.count("INSERTION") == 2, mutation_types

    def test_equal_length_offset_uses_codon_alignment_events(self):
        """Compensating offset cases should count the real indel events, not a mismatch cascade."""
        from app.services.sequence.sequence_service import call_mutations_against_wt

        # WT:  ATG GAA TTT GCT CCA = M E F A P
        # Var: ATG AAA GAA GCT CCA = M K E A P
        # Real events: insert AAA (K), delete TTT (F)
        wt_cds = "ATGGAATTTGCTCCA"
        var_cds = "ATGAAAGAAGCTCCA"

        mutations, counts = call_mutations_against_wt(wt_cds, var_cds)

        mutation_types = [m.mutation_type for m in mutations]
        assert counts.total == 2, mutation_types
        assert counts.synonymous == 0, mutation_types
        assert counts.nonsynonymous == 2, mutation_types
        assert "INSERTION" in mutation_types, mutation_types
        assert "DELETION" in mutation_types, mutation_types
