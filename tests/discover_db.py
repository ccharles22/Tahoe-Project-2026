"""Quick script to discover DB schema and available test data."""
from app.services.sequence.db_repo import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    # Get column names
    for tbl in ('experiments', 'wild_type_proteins', 'variants', 'generations'):
        cols = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND table_schema = 'public' "
            "ORDER BY ordinal_position"
        ), {"t": tbl}).fetchall()
        print(f"\n=== {tbl} columns ===")
        for c in cols:
            print(f"  {c[0]}")

    # List experiments with WT info
    print("\n=== Experiments ===")
    rows = conn.execute(text(
        "SELECT e.experiment_id, e.wt_id, "
        "w.protein_name, w.uniprot_id, "
        "LENGTH(w.amino_acid_sequence) as aa_len, "
        "LENGTH(w.plasmid_sequence) as plasmid_len "
        "FROM public.experiments e "
        "LEFT JOIN public.wild_type_proteins w ON w.wt_id = e.wt_id "
        "ORDER BY e.experiment_id LIMIT 10"
    )).fetchall()
    for r in rows:
        print(f"  exp_id={r[0]}  wt_id={r[1]}  protein={r[2]}  "
              f"uniprot={r[3]}  aa_len={r[4]}  plasmid_len={r[5]}")

    # Variant counts
    print("\n=== Variant counts per experiment ===")
    rows2 = conn.execute(text(
        "SELECT g.experiment_id, COUNT(v.variant_id) as n_variants, "
        "COUNT(v.assembled_dna_sequence) as n_with_dna "
        "FROM public.variants v "
        "JOIN public.generations g ON g.generation_id = v.generation_id "
        "GROUP BY g.experiment_id ORDER BY g.experiment_id LIMIT 10"
    )).fetchall()
    for r in rows2:
        print(f"  exp_id={r[0]}  variants={r[1]}  with_dna={r[2]}")
