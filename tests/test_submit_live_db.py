"""
Integration test: submit_sequence_processing() against live PostgreSQL.

Runs the full pipeline on experiment 1 in a background thread, polls the
analysis_status column until it completes (or times out), then verifies
that results were written to the database.

Prerequisites:
    - DATABASE_URL must point to a reachable PostgreSQL instance
    - Experiment 1 must exist with at least one variant
    - BioPython must be installed (alignment step)

Usage:
    python -m pytest tests/test_submit_live_db.py -v -s
    python tests/test_submit_live_db.py                     # standalone
    python tests/test_submit_live_db.py --experiment 2      # different experiment
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from sqlalchemy import text

from app.services.sequence.db_repo import get_engine
from app.jobs.run_sequence_processing import (
    submit_sequence_processing,
    run_sequence_processing,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-40s  %(levelname)-7s  %(message)s",
)
logger = logging.getLogger(__name__)

# ── Configurable defaults ────────────────────────────────────────────────
DEFAULT_EXPERIMENT_ID = 1
POLL_INTERVAL_SEC = 2
TIMEOUT_SEC = 600  # 10 minutes — re-runs are slower due to DELETE+INSERT on existing mutations


# ── Helper queries ───────────────────────────────────────────────────────

def _get_analysis_status(engine, experiment_id: int) -> str | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT analysis_status FROM public.experiments WHERE experiment_id = :eid"),
            {"eid": experiment_id},
        ).fetchone()
    return row[0] if row else None


def _count_variants(engine, experiment_id: int) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM public.variants v
                JOIN public.generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                  AND v.assembled_dna_sequence IS NOT NULL
            """),
            {"eid": experiment_id},
        ).fetchone()
    return row[0] if row else 0


def _count_variants_with_protein(engine, experiment_id: int) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM public.variants v
                JOIN public.generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                  AND v.protein_sequence IS NOT NULL
            """),
            {"eid": experiment_id},
        ).fetchone()
    return row[0] if row else 0


def _count_mutations(engine, experiment_id: int) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM public.mutations m
                JOIN public.variants v ON v.variant_id = m.variant_id
                JOIN public.generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()
    return row[0] if row else 0


def _count_metrics(engine, experiment_id: int) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM public.metrics m
                JOIN public.variants v ON v.variant_id = m.variant_id
                JOIN public.generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()
    return row[0] if row else 0


def _count_vsa(engine, experiment_id: int) -> int:
    """Count variant_sequence_analysis rows for this experiment."""
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM public.variant_sequence_analysis vsa
                JOIN public.variants v ON v.variant_id = vsa.variant_id
                JOIN public.generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
            """),
            {"eid": experiment_id},
        ).fetchone()
    return row[0] if row else 0


# ── Main test runner ─────────────────────────────────────────────────────

def run_live_test(experiment_id: int, force_reprocess: bool = False) -> bool:
    """
    Submits the pipeline in a background thread, polls for completion,
    and verifies database results.

    On re-runs where the experiment is already ANALYSED, skips the
    pipeline and just verifies existing DB state (fast path).
    Use force_reprocess=True to reprocess all variants from scratch.

    Returns True if all checks pass, False otherwise.
    """
    engine = get_engine()
    ok = True

    print(f"\n{'='*70}")
    print(f"  LIVE DB TEST — submit_sequence_processing(experiment_id={experiment_id})")
    print(f"{'='*70}")

    # ── Pre-flight checks ────────────────────────────────────────────────
    total_variants = _count_variants(engine, experiment_id)
    if total_variants == 0:
        print(f"\n  [SKIP] No variants with DNA found for experiment {experiment_id}.")
        return False

    print(f"\n  [1] Pre-flight")
    print(f"      Variants with DNA : {total_variants}")
    old_status = _get_analysis_status(engine, experiment_id)
    print(f"      Current status    : {old_status}")

    # Reset stale ANALYSIS_RUNNING left by a crashed previous run
    if old_status == "ANALYSIS_RUNNING":
        print(f"      Resetting stale ANALYSIS_RUNNING → None")
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE public.experiments SET analysis_status = NULL WHERE experiment_id = :eid"),
                {"eid": experiment_id},
            )
        old_status = None

    # ── Submit background processing ─────────────────────────────────────
    print(f"\n  [2] Submitting background thread...")
    t0 = time.perf_counter()
    thread = submit_sequence_processing(experiment_id, force_reprocess=force_reprocess)
    submit_elapsed = time.perf_counter() - t0
    print(f"      Returned in {submit_elapsed:.3f}s (thread={thread.name})")

    if submit_elapsed > 1.0:
        print(f"      [FAIL] submit took > 1s — should be non-blocking")
        ok = False
    else:
        print(f"      [PASS] Non-blocking return")

    # ── Poll for completion ──────────────────────────────────────────────
    print(f"\n  [3] Polling analysis_status (timeout={TIMEOUT_SEC}s)...")
    deadline = time.perf_counter() + TIMEOUT_SEC
    final_statuses = {"ANALYSED", "ANALYSED_WITH_ERRORS", "FAILED"}
    status = None

    while time.perf_counter() < deadline:
        status = _get_analysis_status(engine, experiment_id)
        if status in final_statuses:
            break
        time.sleep(POLL_INTERVAL_SEC)

    elapsed = time.perf_counter() - t0
    print(f"      Final status : {status}")
    print(f"      Elapsed      : {elapsed:.1f}s")

    if status not in final_statuses:
        print(f"      [FAIL] Timed out — status is still '{status}'")
        return False

    if status == "FAILED":
        print(f"      [WARN] Pipeline finished with FAILED status — check logs")
        ok = False
    elif status == "ANALYSED_WITH_ERRORS":
        print(f"      [WARN] Some variants had errors")
    else:
        print(f"      [PASS] Status is ANALYSED")

    # ── Verify database writes ───────────────────────────────────────────
    print(f"\n  [4] Verifying database writes...")

    proteins = _count_variants_with_protein(engine, experiment_id)
    mutations = _count_mutations(engine, experiment_id)
    metrics = _count_metrics(engine, experiment_id)

    print(f"      Variants with protein_sequence : {proteins}/{total_variants}")
    print(f"      Mutation rows                  : {mutations}")
    print(f"      Metric rows                    : {metrics}")

    if proteins == 0:
        print(f"      [FAIL] No protein sequences written")
        ok = False
    else:
        print(f"      [PASS] Protein sequences present")

    # Mutations are optional (WT-identical variants have 0), but we expect some
    if mutations > 0:
        print(f"      [PASS] Mutations recorded")
    else:
        print(f"      [WARN] No mutations found (possible if all variants are WT-identical)")

    # Should have 3 metric rows per variant (synonymous, nonsynonymous, total)
    expected_metrics = total_variants * 3
    if metrics >= expected_metrics:
        print(f"      [PASS] Metrics present ({metrics} rows, expected ≥{expected_metrics})")
    elif metrics > 0:
        print(f"      [WARN] Fewer metrics than expected ({metrics} vs {expected_metrics})")
    else:
        print(f"      [FAIL] No metrics written")
        ok = False

    # VSA table (may not exist in all schemas)
    try:
        vsa_count = _count_vsa(engine, experiment_id)
        print(f"      VSA rows                       : {vsa_count}")
        if vsa_count > 0:
            print(f"      [PASS] variant_sequence_analysis populated")
        else:
            print(f"      [WARN] No VSA rows (table may not have been created yet)")
    except Exception:
        print(f"      [SKIP] variant_sequence_analysis table not found")

    # ── Thread should be finished ────────────────────────────────────────
    print(f"\n  [5] Thread status")
    if thread is None:
        print(f"      [SKIP] No thread launched (fast path)")
    else:
        thread.join(timeout=5)
        if thread.is_alive():
            print(f"      [FAIL] Thread still alive after status is terminal")
            ok = False
        else:
            print(f"      [PASS] Thread exited cleanly")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    result = "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"
    print(f"  {result}  ({elapsed:.1f}s)")
    print(f"{'='*70}\n")

    return ok


# ── pytest entry point ───────────────────────────────────────────────────

def test_live_submit_sequence_processing():
    """pytest-compatible wrapper: runs the live DB test on experiment 1."""
    assert run_live_test(DEFAULT_EXPERIMENT_ID), "Live DB integration test failed"


# ── Standalone entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Live DB integration test for submit_sequence_processing"
    )
    parser.add_argument(
        "--experiment", type=int, default=DEFAULT_EXPERIMENT_ID,
        help=f"Experiment ID to test (default: {DEFAULT_EXPERIMENT_ID})",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force reprocessing of all variants (slow on re-runs)",
    )
    args = parser.parse_args()
    success = run_live_test(args.experiment, force_reprocess=args.force)
    sys.exit(0 if success else 1)
