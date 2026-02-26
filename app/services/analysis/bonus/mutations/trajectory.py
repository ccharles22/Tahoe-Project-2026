from __future__ import annotations

import argparse
import pandas as pd

from app.services.analysis.bonus.database.postgres import db_conn


def query_top_variants(conn, generation_id: int, limit: int = 10) -> pd.DataFrame:
    """Top variants by activity_score in a given generation."""
    return pd.read_sql_query(
        """
        SELECT
          v.variant_id,
          v.generation_id,
          v.plasmid_variant_index,
          m.value AS activity_score
        FROM variants v
        JOIN metrics m
          ON m.variant_id = v.variant_id
         AND m.generation_id = v.generation_id
         AND m.metric_name = 'activity_score'
         AND m.metric_type = 'derived'
        WHERE v.generation_id = %s
        ORDER BY m.value DESC
        LIMIT %s
        """,
        conn,
        params=(generation_id, limit),
    )


def query_lineage_chain(conn, variant_id: int) -> pd.DataFrame:
    """Recursive CTE walk from leaf to root via parent_variant_id."""
    return pd.read_sql_query(
        """
        WITH RECURSIVE chain AS (
          SELECT v.variant_id, v.parent_variant_id, v.generation_id, 0 AS depth
          FROM variants v
          WHERE v.variant_id = %s
          UNION ALL
          SELECT p.variant_id, p.parent_variant_id, p.generation_id, c.depth + 1
          FROM chain c
          JOIN variants p ON p.variant_id = c.parent_variant_id
          WHERE c.parent_variant_id IS NOT NULL
        )
        SELECT variant_id, parent_variant_id, generation_id, depth
        FROM chain
        ORDER BY depth ASC
        """,
        conn,
        params=(variant_id,),
    )


def query_cumulative_nonsyn_for_chain(conn, chain_variant_ids: list[int]) -> pd.DataFrame:
    """
    Per-variant non-synonymous protein mutation counts for the given chain.
    Counts are per-node, not cumulative — see build_trajectory_dataframe
    for the cumulative accumulation logic.
    """
    # Builds a temporary VALUES table for ordering
    ids_sql = ",".join(str(int(x)) for x in chain_variant_ids)

    return pd.read_sql_query(
        f"""
        WITH chain AS (
          SELECT variant_id, generation_id
          FROM variants
          WHERE variant_id IN ({ids_sql})
        ),
        muts AS (
          SELECT
            m.variant_id,
            m.position,
            m.original,
            m.mutated
          FROM mutations m
          WHERE m.variant_id IN ({ids_sql})
            AND m.mutation_type='protein'
            AND m.is_synonymous IS FALSE
        )
        SELECT
          c.variant_id,
          c.generation_id,
          COUNT(DISTINCT (m.position, m.original, m.mutated)) AS nonsyn_count
        FROM chain c
        LEFT JOIN muts m ON m.variant_id = c.variant_id
        GROUP BY c.variant_id, c.generation_id
        ORDER BY c.generation_id ASC
        """,
        conn,
    )


def build_trajectory_dataframe(conn, top_variant_id: int) -> pd.DataFrame:
    """Walks a variant's lineage root-to-leaf, accumulating unique non-synonymous mutations."""
    chain = query_lineage_chain(conn, top_variant_id)
    chain_ids = chain["variant_id"].astype(int).tolist()

    # Accumulate unique mutations in Python rather than complex SQL window state
    muts = pd.read_sql_query(
        """
        SELECT variant_id, position, original, mutated
        FROM mutations
        WHERE mutation_type='protein' AND is_synonymous IS FALSE
          AND variant_id = ANY(%s)
        """,
        conn,
        params=(chain_ids,),
    )

    seen = set()
    rows = []
    # chain is depth-ordered leaf->root, so reverse to walk root->leaf
    chain_rev = chain.sort_values("depth", ascending=False)

    for _, node in chain_rev.iterrows():
        vid = int(node["variant_id"])
        gen = int(node["generation_id"])
        node_muts = muts[muts["variant_id"] == vid]

        for _, r in node_muts.iterrows():
            seen.add((int(r["position"]), str(r["original"]), str(r["mutated"])))

        rows.append({"variant_id": vid, "generation_id": gen, "cumulative_nonsyn": len(seen)})

    df = pd.DataFrame(rows).sort_values("generation_id")
    return df


def main():
    ap = argparse.ArgumentParser(description="Compute lineage-based mutation accumulation trajectory for top variants.")
    ap.add_argument("--generation-id", type=int, required=True, help="Generation to select Top-N variants from.")
    ap.add_argument("--top-n", type=int, default=5)
    args = ap.parse_args()

    with db_conn() as conn:
        top = query_top_variants(conn, args.generation_id, limit=args.top_n)
        if top.empty:
            raise SystemExit("No top variants found (is activity_score computed and stored in metrics?)")

        all_rows = []
        for _, r in top.iterrows():
            vid = int(r["variant_id"])
            df_traj = build_trajectory_dataframe(conn, vid)
            df_traj["top_variant_id"] = vid
            df_traj["top_variant_label"] = r["plasmid_variant_index"]
            all_rows.append(df_traj)

        out = pd.concat(all_rows, ignore_index=True)
        print(out.to_string(index=False))


if __name__ == "__main__":
    main()