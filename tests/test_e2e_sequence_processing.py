"""
End-to-end test: load example data → insert into DB → run pipeline → assert completion < 60s.

Usage:
    python -m tests.test_e2e_sequence_processing

Requires:
    - DATABASE_URL set in .env or environment
    - Example data at C:\\Users\\Patri\\Downloads\\Example_Data\\Example_Data\\
"""
from __future__ import annotations

import json
import logging
import sys
import time

from sqlalchemy import text

from app.config import settings
from app.services.sequence.db_repo import get_engine
from app.jobs.run_sequence_processing import run_sequence_processing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)-8s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("e2e_test")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
EXAMPLE_DIR = r"C:\Users\Patri\Downloads\Example_Data\Example_Data"
JSON_PATH = f"{EXAMPLE_DIR}\\DE_BSU_Pol_Batch_1.json"
FASTA_PATH = f"{EXAMPLE_DIR}\\pET-28a_BSU_DNA_Pol_I_WT.fa"


def _read_fasta_sequence(path: str) -> str:
    """Read a single-sequence FASTA file and return the DNA string."""
    with open(path) as f:
        lines = f.readlines()
    return "".join(l.strip() for l in lines if not l.startswith(">"))


def _cleanup(engine, experiment_id: int, original_plasmid: str | None = None) -> None:
    """Remove all rows created by this test (reverse insertion order)."""
    with engine.begin() as conn:
        # 1. mutations (FK → variant_sequence_analysis)
        conn.execute(text("""
            DELETE FROM mutations
            WHERE vsa_id IN (
                SELECT vsa_id FROM variant_sequence_analysis
                WHERE variant_id IN (
                    SELECT v.variant_id
                    FROM variants v
                    JOIN generations g ON g.generation_id = v.generation_id
                    WHERE g.experiment_id = :eid
                )
            )
        """), {"eid": experiment_id})

        # 2. variant_sequence_analysis
        conn.execute(text("""
            DELETE FROM variant_sequence_analysis
            WHERE variant_id IN (
                SELECT v.variant_id
                FROM variants v
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
            )
        """), {"eid": experiment_id})

        # 3. metrics
        conn.execute(text("""
            DELETE FROM metrics
            WHERE generation_id IN (
                SELECT generation_id FROM generations WHERE experiment_id = :eid
            )
        """), {"eid": experiment_id})

        # 4. variants
        conn.execute(text("""
            DELETE FROM variants
            WHERE generation_id IN (
                SELECT generation_id FROM generations WHERE experiment_id = :eid
            )
        """), {"eid": experiment_id})

        # 5. generations
        conn.execute(text(
            "DELETE FROM generations WHERE experiment_id = :eid"
        ), {"eid": experiment_id})

        # 6. experiment_metadata
        conn.execute(text(
            "DELETE FROM experiment_metadata WHERE experiment_id = :eid"
        ), {"eid": experiment_id})

        # 7. experiment
        conn.execute(text(
            "DELETE FROM experiments WHERE experiment_id = :eid"
        ), {"eid": experiment_id})

        # 8. Restore original WT plasmid sequence
        if original_plasmid is not None:
            conn.execute(text(
                "UPDATE wild_type_proteins SET plasmid_sequence = :p WHERE wt_id = 3"
            ), {"p": original_plasmid})

    logger.info("Cleanup complete for experiment %d", experiment_id)


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_test_data(engine) -> tuple[int, int, str]:
    """
    Insert experiment, generations, variants from example data.
    Updates wt_id=3 plasmid to full sequence from FASTA (restores in cleanup).
    Reuses existing user_id=23 and wt_id=3.
    Returns (experiment_id, variant_count, original_plasmid).
    """
    USER_ID = 23
    WT_ID = 3

    # Read full WT plasmid from FASTA so mapping coordinates are correct
    wt_plasmid_full = _read_fasta_sequence(FASTA_PATH)

    # Save original plasmid and update to full plasmid
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT plasmid_sequence FROM wild_type_proteins WHERE wt_id = :wid"
        ), {"wid": WT_ID}).fetchone()
        original_plasmid = row[0]

        conn.execute(text(
            "UPDATE wild_type_proteins SET plasmid_sequence = :p WHERE wt_id = :wid"
        ), {"p": wt_plasmid_full, "wid": WT_ID})

    # Load example data
    with open(JSON_PATH) as f:
        records = json.load(f)
    logger.info("Loaded %d records from example data", len(records))

    with engine.begin() as conn:
        # Create experiment
        result = conn.execute(text("""
            INSERT INTO experiments (user_id, wt_id, name, description, analysis_status)
            VALUES (:uid, :wid, :name, :desc, 'UPLOADED')
            RETURNING experiment_id
        """), {
            "uid": USER_ID,
            "wid": WT_ID,
            "name": "E2E Pipeline Test - BSU Pol Batch 1",
            "desc": "Automated end-to-end pipeline test with example data",
        })
        experiment_id = result.scalar_one()

        # Create generations (0-10)
        gen_map: dict[int, int] = {}
        for gen_num in range(11):
            result = conn.execute(text("""
                INSERT INTO generations (experiment_id, generation_number)
                VALUES (:eid, :gnum)
                RETURNING generation_id
            """), {"eid": experiment_id, "gnum": gen_num})
            gen_map[gen_num] = result.scalar_one()

        # Insert variants (skip controls)
        variant_count = 0
        pvi_to_vid: dict[int, int] = {}

        sorted_records = sorted(records, key=lambda r: (
            r["Directed_Evolution_Generation"],
            r["Plasmid_Variant_Index"],
        ))

        for rec in sorted_records:
            if rec.get("Control"):
                continue

            gen_num = rec["Directed_Evolution_Generation"]
            pvi = rec["Plasmid_Variant_Index"]
            parent_pvi = rec.get("Parent_Plasmid_Variant", -1)
            dna = rec["Assembled_DNA_Sequence"]

            parent_vid = pvi_to_vid.get(parent_pvi)

            result = conn.execute(text("""
                INSERT INTO variants
                    (generation_id, parent_variant_id, plasmid_variant_index,
                     assembled_dna_sequence)
                VALUES (:gid, :pvid, :pvi, :dna)
                RETURNING variant_id
            """), {
                "gid": gen_map[gen_num],
                "pvid": parent_vid,
                "pvi": str(pvi),
                "dna": dna,
            })
            vid = result.scalar_one()
            pvi_to_vid[pvi] = vid
            variant_count += 1

    logger.info(
        "Created: experiment_id=%d, variants=%d (user=%d, wt=%d)",
        experiment_id, variant_count, USER_ID, WT_ID,
    )
    return experiment_id, variant_count, original_plasmid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    engine = get_engine()
    logger.info("Database: connected")

    experiment_id = None
    original_plasmid = None
    try:
        # Setup
        experiment_id, variant_count, original_plasmid = setup_test_data(engine)
        logger.info("=" * 60)
        logger.info("STARTING PIPELINE — %d variants", variant_count)
        logger.info("=" * 60)

        # Run pipeline and measure time
        t0 = time.perf_counter()
        run_sequence_processing(experiment_id)
        elapsed = time.perf_counter() - t0

        logger.info("=" * 60)
        logger.info(
            "PIPELINE COMPLETED in %.1fs (%.0f ms/variant)",
            elapsed, (elapsed / max(1, variant_count)) * 1000,
        )
        logger.info("=" * 60)

        # Verify results
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT analysis_status FROM experiments WHERE experiment_id = :eid"
            ), {"eid": experiment_id}).fetchone()
            status = row[0] if row else "NOT FOUND"

            count_row = conn.execute(text("""
                SELECT COUNT(*) FROM variant_sequence_analysis
                WHERE variant_id IN (
                    SELECT v.variant_id FROM variants v
                    JOIN generations g ON g.generation_id = v.generation_id
                    WHERE g.experiment_id = :eid
                )
            """), {"eid": experiment_id}).fetchone()
            analysed = count_row[0] if count_row else 0

            mut_row = conn.execute(text("""
                SELECT COUNT(*) FROM mutations
                WHERE vsa_id IN (
                    SELECT vsa_id FROM variant_sequence_analysis
                    WHERE variant_id IN (
                        SELECT v.variant_id FROM variants v
                        JOIN generations g ON g.generation_id = v.generation_id
                        WHERE g.experiment_id = :eid
                    )
                )
            """), {"eid": experiment_id}).fetchone()
            total_muts = mut_row[0] if mut_row else 0

        logger.info("Experiment status: %s", status)
        logger.info("Variants analysed: %d / %d", analysed, variant_count)
        logger.info("Total mutations found: %d", total_muts)

        # Assertions
        assert status in ("ANALYSED", "ANALYSED_WITH_ERRORS"), (
            f"Expected ANALYSED or ANALYSED_WITH_ERRORS, got {status}"
        )
        assert analysed == variant_count, (
            f"Expected {variant_count} analyses, got {analysed}"
        )
        assert elapsed < 60, (
            f"Pipeline took {elapsed:.1f}s — must complete under 60s"
        )

        print()
        print("=" * 60)
        print(f"  PASS — {variant_count} variants in {elapsed:.1f}s "
              f"({elapsed/variant_count*1000:.0f} ms/variant)")
        print(f"  Status: {status}")
        print(f"  Mutations: {total_muts}")
        print("=" * 60)

    finally:
        # Always clean up
        if experiment_id is not None:
            logger.info("Cleaning up test data...")
            try:
                _cleanup(engine, experiment_id, original_plasmid)
            except Exception:
                logger.exception("Cleanup failed — manual cleanup needed")


if __name__ == "__main__":
    main()
