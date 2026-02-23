"""
Consolidated database inspection script.

Shows experiment status, variant protein sequences, analysis metadata,
mutations (both JSONB and table), metrics, WT mapping cache, and table
schema information for a given experiment.

Usage:
    python -m scripts.show_db_results [--experiment N] [--variant V] [--limit L]
"""

import argparse
import json

from sqlalchemy import text
from app.config import settings
from app.services.sequence.db_repo import get_engine


def parse_args():
    p = argparse.ArgumentParser(description="Inspect database results")
    p.add_argument("--experiment", type=int, default=2, help="Experiment ID (default: 2)")
    p.add_argument("--variant", type=int, default=None, help="Variant ID to inspect (default: first variant found)")
    p.add_argument("--limit", type=int, default=5, help="Max rows for list queries (default: 5)")
    return p.parse_args()


def section(title: str):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def show_experiment_status(conn, experiment_id: int):
    section("1. EXPERIMENT STATUS")
    row = conn.execute(text(
        "SELECT analysis_status, extra_metadata->>'analysis_status' "
        "FROM public.experiments WHERE experiment_id = :eid"
    ), {"eid": experiment_id}).fetchone()
    if row:
        print(f"  analysis_status column: {row[0]}")
        print(f"  extra_metadata status:  {row[1]}")
    else:
        print(f"  (no experiment with id {experiment_id})")


def show_variant_proteins(conn, experiment_id: int, limit: int):
    section("2. VARIANT PROTEIN SEQUENCES")
    rows = conn.execute(text(
        "SELECT v.variant_id, LENGTH(v.protein_sequence), "
        "LEFT(v.protein_sequence, 40) "
        "FROM public.variants v "
        "JOIN public.generations g ON g.generation_id = v.generation_id "
        "WHERE g.experiment_id = :eid ORDER BY v.variant_id LIMIT :lim"
    ), {"eid": experiment_id, "lim": limit}).fetchall()
    for r in rows:
        print(f"  variant {r[0]}: {r[1]} aa  |  {r[2]}...")
    if not rows:
        print("  (no variants found)")
    return rows[0][0] if rows else None


def show_variant_analysis_metadata(conn, variant_id: int):
    section(f"3. VARIANT ANALYSIS METADATA (variant {variant_id})")
    row = conn.execute(text(
        "SELECT extra_metadata->'sequence_analysis' "
        "FROM public.variants WHERE variant_id = :vid"
    ), {"vid": variant_id}).fetchone()
    if not row or not row[0]:
        print("  (no analysis metadata)")
        return
    a = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    print(f"  strand:       {a.get('strand')}")
    print(f"  frame:        {a.get('frame')}")
    print(f"  cds_start:    {a.get('cds_start_0based')}")
    print(f"  cds_end:      {a.get('cds_end_0based_excl')}")
    prot = a.get("protein_aa", "") or ""
    print(f"  protein_aa:   {prot[:50]}...")
    qc = a.get("qc", {})
    print(f"  qc_ambig:     {qc.get('has_ambiguous_bases')}")
    print(f"  qc_frameshift:{qc.get('has_frameshift')}")
    print(f"  qc_prem_stop: {qc.get('has_premature_stop')}")
    c = a.get("mutation_counts", {})
    print(f"  syn:          {c.get('synonymous')}")
    print(f"  nonsyn:       {c.get('nonsynonymous')}")
    print(f"  total:        {c.get('total')}")
    muts = a.get("mutations", [])
    print(f"  mutations:    {len(muts)} records in JSONB")
    for m in muts[:3]:
        print(f"    {m['mutation_type']:16} pos={m['aa_position_1based']}  "
              f"{m.get('wt_aa') or '-'}>{m.get('var_aa') or '-'}")
    if len(muts) > 3:
        print(f"    ... and {len(muts) - 3} more")


def show_mutations_table(conn, variant_id: int, experiment_id: int, limit: int):
    section(f"4. MUTATIONS TABLE (variant {variant_id})")
    rows = conn.execute(text(
        "SELECT mutation_type, position, original, mutated, is_synonymous, annotation "
        "FROM public.mutations WHERE variant_id = :vid ORDER BY position LIMIT :lim"
    ), {"vid": variant_id, "lim": limit}).fetchall()
    if rows:
        for r in rows:
            syn = {True: "Yes", False: "No", None: "N/A"}.get(r[4], "?")
            ann = (r[5] or "")[:40]
            print(f"  pos={r[1]} {r[2]}>{r[3]} type={r[0]} syn={syn} ann={ann}")
    else:
        print("  (no rows — mutations may be stored in variants.extra_metadata JSONB)")

    # Also show JSONB mutation data for the experiment
    section(f"4b. EXTRA METADATA MUTATIONS (experiment {experiment_id}, first {limit})")
    rows = conn.execute(text(
        "SELECT v.variant_id, "
        "  v.extra_metadata->'sequence_analysis'->'mutations' AS muts_json, "
        "  v.extra_metadata->'sequence_analysis'->'mutation_counts' AS counts_json "
        "FROM public.variants v "
        "JOIN public.generations g ON g.generation_id = v.generation_id "
        "WHERE g.experiment_id = :eid AND v.extra_metadata IS NOT NULL "
        "ORDER BY v.variant_id LIMIT :lim"
    ), {"eid": experiment_id, "lim": limit}).fetchall()
    for r in rows:
        print(f"  variant {r[0]}:")
        print(f"    mutations: {str(r[1])[:200]}")
        print(f"    counts:    {r[2]}")
    if not rows:
        print("  (no metadata found)")


def show_metrics(conn, variant_id: int):
    section(f"5. METRICS TABLE (variant {variant_id})")
    rows = conn.execute(text(
        "SELECT metric_name, value, unit "
        "FROM public.metrics WHERE variant_id = :vid ORDER BY metric_name"
    ), {"vid": variant_id}).fetchall()
    for r in rows:
        print(f"  {r[0]}: {r[1]} {r[2]}")
    if not rows:
        print("  (no metrics)")


def show_wt_mapping_cache(conn, experiment_id: int):
    section("6. WT MAPPING CACHE")
    row = conn.execute(text(
        "SELECT field_value FROM public.experiment_metadata "
        "WHERE experiment_id = :eid AND field_name = 'wt_mapping_json'"
    ), {"eid": experiment_id}).fetchone()
    if row:
        wt = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        print(f"  strand:    {wt.get('strand')}")
        print(f"  frame:     {wt.get('frame')}")
        print(f"  identity:  {wt.get('match_identity_pct')}%")
        print(f"  cds_len:   {len(wt.get('wt_cds_dna', ''))} bp")
        print(f"  score:     {wt.get('alignment_score')}")
    else:
        print("  (no cache found)")


def show_table_schema(conn):
    section("7. MUTATIONS TABLE SCHEMA")
    rows = conn.execute(text(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'mutations' "
        "ORDER BY ordinal_position"
    )).fetchall()
    for r in rows:
        print(f"  {r[0]:<20} {r[1]:<20} nullable={r[2]:<5} default={r[3]}")

    print()
    print("  Constraints:")
    rows = conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) "
        "FROM pg_constraint "
        "WHERE conrelid = 'public.mutations'::regclass"
    )).fetchall()
    for r in rows:
        print(f"    {r[0]}: {r[1]}")

    row = conn.execute(text("SELECT COUNT(*) FROM public.mutations")).fetchone()
    print(f"\n  Total mutations in table: {row[0]}")


def main():
    args = parse_args()
    engine = get_engine()

    with engine.connect() as conn:
        show_experiment_status(conn, args.experiment)
        first_variant = show_variant_proteins(conn, args.experiment, args.limit)

        variant_id = args.variant or first_variant
        if variant_id is None:
            print("\n  No variants found — skipping variant-specific queries.")
            return

        show_variant_analysis_metadata(conn, variant_id)
        show_mutations_table(conn, variant_id, args.experiment, args.limit)
        show_metrics(conn, variant_id)
        show_wt_mapping_cache(conn, args.experiment)
        show_table_schema(conn)


if __name__ == "__main__":
    main()
