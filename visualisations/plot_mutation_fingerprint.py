from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import plotly.express as px

from analysis.database.postgres import get_connection


def fetch_lineage(conn, variant_id: int) -> pd.DataFrame:
    """Recursive CTE: leaf-to-root ancestor chain."""
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
        ORDER BY depth DESC
        """,
        conn,
        params=(variant_id,),
    )


def fetch_mutations_for_variants(conn, variant_ids: list[int]) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT variant_id, position, original, mutated
        FROM mutations
        WHERE mutation_type='protein' AND is_synonymous IS FALSE
          AND variant_id = ANY(%s)
        """,
        conn,
        params=(variant_ids,),
    )


def compute_introduction_generation(chain: pd.DataFrame, muts: pd.DataFrame) -> pd.DataFrame:
    """Walks root-to-leaf and records the generation each mutation first appeared."""
    chain_sorted = chain.sort_values("depth", ascending=False)

    first_seen: dict[tuple[int, str, str], int] = {}
    for _, node in chain_sorted.iterrows():
        vid = int(node["variant_id"])
        gen = int(node["generation_id"])
        node_muts = muts[muts["variant_id"] == vid]

        for _, r in node_muts.iterrows():
            key = (int(r["position"]), str(r["original"]), str(r["mutated"]))
            if key not in first_seen:
                first_seen[key] = gen

    out = pd.DataFrame(
        [{"position": k[0], "original": k[1], "mutated": k[2], "introduced_generation": g}
         for k, g in first_seen.items()]
    )
    if out.empty:
        return out

    out["label"] = out["original"] + out["position"].astype(str) + out["mutated"]
    return out.sort_values(["introduced_generation", "position"])


def plot_mutation_fingerprint(
    variant_id: int,
    out_path: Path | str = "outputs/mutation_fingerprint.html",
) -> Path:
    """Strip chart: x = amino-acid position, colour = generation the mutation was introduced."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        chain = fetch_lineage(conn, variant_id)
        if chain.empty:
            raise RuntimeError("Variant not found.")

        lineage_ids = chain["variant_id"].astype(int).tolist()
        muts = fetch_mutations_for_variants(conn, lineage_ids)

    df = compute_introduction_generation(chain, muts)
    if df.empty:
        raise RuntimeError("No non-synonymous protein mutations found in lineage.")

    df["y"] = 1

    fig = px.scatter(
        df,
        x="position",
        y="y",
        color="introduced_generation",
        hover_data=["label", "introduced_generation"],
        title=f"Mutation Fingerprint (Variant {variant_id}) — colored by generation introduced",
    )
    fig.update_traces(marker=dict(size=10))
    fig.update_layout(
        yaxis=dict(visible=False),
        xaxis_title="Amino acid position",
        legend_title="Introduced in gen",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Mutation fingerprint plot coloured by generation introduced.")
    ap.add_argument("--variant-id", type=int, required=True)
    ap.add_argument("--out", default="outputs/mutation_fingerprint.html")
    args = ap.parse_args()

    out = plot_mutation_fingerprint(args.variant_id, args.out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()