from __future__ import annotations

import argparse
from typing import Optional

import pandas as pd

from app.services.analysis.bonus.database.postgres import db_conn, detect_wt_id_for_generation


def query_domain_enrichment(conn, generation_id: int, wt_id: int) -> pd.DataFrame:
    """
    Joins protein mutations against UniProt feature intervals (protein_features)
    to produce per-domain non-synonymous/synonymous counts and density.
    """
    return pd.read_sql_query(
        """
        SELECT
          v.generation_id,
          pf.feature_type,
          COALESCE(pf.description, pf.feature_type) AS domain_label,
          COUNT(*) FILTER (WHERE m.is_synonymous IS FALSE) AS nonsyn_count,
          COUNT(*) FILTER (WHERE m.is_synonymous IS TRUE)  AS syn_count,
          COUNT(*) AS total_protein_mutations,
          (pf.end_position - pf.start_position + 1) AS domain_length,
          COUNT(*) FILTER (WHERE m.is_synonymous IS FALSE)::float
            / NULLIF((pf.end_position - pf.start_position + 1), 0) AS nonsyn_per_residue
        FROM variants v
        JOIN mutations m
          ON m.variant_id = v.variant_id
         AND m.mutation_type = 'protein'
        JOIN protein_features pf
          ON pf.wt_id = %s
         AND m.position BETWEEN pf.start_position AND pf.end_position
        WHERE v.generation_id = %s
          AND pf.feature_type IN ('Domain', 'Region')
        GROUP BY
          v.generation_id, pf.feature_type, domain_label, pf.start_position, pf.end_position
        ORDER BY nonsyn_count DESC
        """,
        conn,
        params=(wt_id, generation_id),
    )


def main():
    ap = argparse.ArgumentParser(description="Query domain-level mutation enrichment (needs wt_id or auto-detect).")
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--wt-id", type=int, default=None, help="WT ID used by protein_features.wt_id (if auto-detect fails).")
    args = ap.parse_args()

    with db_conn() as conn:
        wt_id = args.wt_id if args.wt_id is not None else detect_wt_id_for_generation(conn, args.generation_id)
        if wt_id is None:
            raise SystemExit(
                "Could not auto-detect wt_id for this generation. "
                "Run again with: --wt-id <WT_ID>"
            )

        df = query_domain_enrichment(conn, args.generation_id, wt_id)
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()