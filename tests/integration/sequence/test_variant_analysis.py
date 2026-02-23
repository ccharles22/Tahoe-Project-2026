"""
Integration test: sequence_service.py variant analysis against live PostgreSQL.

Tests the full pipeline end-to-end using experiment_id=2 (30 variants, smallest set):
    1. Loads WT reference from DB (protein + plasmid)
    2. Maps WT gene in plasmid (6-frame alignment)
    3. Extracts & translates variant CDS
    4. Calls mutations against WT
    5. Prints summary results

Usage:
    python -m scripts.test_variant_analysis
    python -m scripts.test_variant_analysis --experiment 1
"""
from __future__ import annotations

import argparse
import sys
import time

from app.services.sequence.db_repo import get_engine, get_wt_reference, list_variants_by_experiment
from app.services.sequence.sequence_service import (
    map_wt_gene_in_plasmid,
    process_variant_plasmid,
    call_mutations_against_wt,
)


def run_test(experiment_id: int, max_variants: int = 5) -> None:
    engine = get_engine()

    # ── Step 1: Load WT reference ────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  VARIANT ANALYSIS TEST — Experiment {experiment_id}")
    print(f"{'='*70}")

    t0 = time.perf_counter()
    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id)
    print(f"\n[1] WT Reference loaded")
    print(f"    Protein length : {len(wt_protein)} aa")
    print(f"    Plasmid length : {len(wt_plasmid)} bp")
    print(f"    Protein (first 60): {wt_protein[:60]}...")

    # ── Step 2: Map WT gene in plasmid ──────────────────────────────────
    print(f"\n[2] Mapping WT gene in plasmid (6-frame alignment)...")
    t1 = time.perf_counter()
    wt_mapping = map_wt_gene_in_plasmid(wt_protein, wt_plasmid)
    t2 = time.perf_counter()
    print(f"    Strand          : {wt_mapping.strand}")
    print(f"    Frame           : {wt_mapping.frame}")
    print(f"    CDS coords      : [{wt_mapping.cds_start_0based}, {wt_mapping.cds_end_0based_excl})")
    print(f"    CDS length      : {len(wt_mapping.wt_cds_dna)} bp")
    print(f"    Identity        : {wt_mapping.match_identity_pct:.2f}%")
    print(f"    Alignment score : {wt_mapping.alignment_score:.1f}")
    print(f"    Time            : {t2 - t1:.2f}s")

    # ── Step 3: Load variants ───────────────────────────────────────────
    variants = list_variants_by_experiment(engine, experiment_id)
    print(f"\n[3] Loaded {len(variants)} variants from database")

    if max_variants and len(variants) > max_variants:
        variants = variants[:max_variants]
        print(f"    (testing first {max_variants} only)")

    # ── Step 4: Process each variant ────────────────────────────────────
    print(f"\n[4] Processing variants...")
    print(f"    {'ID':>6}  {'Protein':>8}  {'Muts':>5}  {'Syn':>4}  {'NonSyn':>6}  {'QC Flags'}")
    print(f"    {'─'*6}  {'─'*8}  {'─'*5}  {'─'*4}  {'─'*6}  {'─'*30}")

    results_summary = []
    for vid, dna_seq in variants:
        try:
            # Extract CDS & translate
            vresult = process_variant_plasmid(
                dna_seq,
                wt_mapping,
                fallback_search=False,
            )

            # Call mutations
            if vresult.cds_dna and wt_mapping.wt_cds_dna:
                mutations, counts = call_mutations_against_wt(
                    wt_mapping.wt_cds_dna,
                    vresult.cds_dna,
                )
            else:
                mutations, counts = [], None

            # QC summary
            qc_flags = []
            if vresult.qc.has_ambiguous_bases:
                qc_flags.append("AMBIG")
            if vresult.qc.has_frameshift:
                qc_flags.append("FRAMESHIFT")
            if vresult.qc.has_premature_stop:
                qc_flags.append("PREM_STOP")
            qc_str = ", ".join(qc_flags) if qc_flags else "OK"

            prot_len = len(vresult.protein_aa) if vresult.protein_aa else 0
            total = counts.total if counts else 0
            syn = counts.synonymous if counts else 0
            nonsyn = counts.nonsynonymous if counts else 0

            print(f"    {vid:>6}  {prot_len:>7}aa  {total:>5}  {syn:>4}  {nonsyn:>6}  {qc_str}")

            results_summary.append({
                "variant_id": vid,
                "protein_len": prot_len,
                "mutations": mutations,
                "counts": counts,
                "qc": qc_str,
            })

        except Exception as e:
            print(f"    {vid:>6}  ERROR: {type(e).__name__}: {e}")

    # ── Step 5: Detailed mutation report for first variant with mutations ─
    for r in results_summary:
        if r["mutations"]:
            print(f"\n[5] Detailed mutations for variant {r['variant_id']}:")
            print(f"    {'Type':<16} {'Pos':>4}  {'WT':>3} → {'Var':>3}  {'WT Codon':>9} → {'Var Codon':>9}  Notes")
            print(f"    {'─'*16} {'─'*4}  {'─'*3}   {'─'*3}  {'─'*9}   {'─'*9}  {'─'*20}")
            for m in r["mutations"][:15]:
                pos = m.aa_position_1based or "-"
                wt_aa = m.wt_aa or "-"
                var_aa = m.var_aa or "-"
                wt_c = m.wt_codon or "-"
                var_c = m.var_codon or "-"
                notes = m.notes or ""
                print(f"    {m.mutation_type:<16} {str(pos):>4}  {wt_aa:>3} → {var_aa:>3}  {wt_c:>9} → {var_c:>9}  {notes}")
            if len(r["mutations"]) > 15:
                print(f"    ... and {len(r['mutations']) - 15} more mutations")
            break

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*70}")
    print(f"  DONE — {len(results_summary)} variants processed in {elapsed:.2f}s")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test variant analysis pipeline")
    parser.add_argument("--experiment", type=int, default=2,
                        help="Experiment ID to test (default: 2, smallest set)")
    parser.add_argument("--max", type=int, default=5,
                        help="Max variants to process (default: 5, 0=all)")
    args = parser.parse_args()
    run_test(args.experiment, args.max or None)
