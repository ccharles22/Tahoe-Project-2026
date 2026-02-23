from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import plotly.express as px

from analysis.database.postgres import get_connection


def plot_domain_enrichment(
    generation_id: Optional[int] = None,
    metric: Literal["nonsyn_count", "nonsyn_per_residue"] = "nonsyn_count",
    out_path: Path | str = "outputs/domain_enrichment_heatmap.html",
) -> Path:
    """Bar chart for a single generation, or cross-generation heatmap when generation_id is None."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    sql = """
      SELECT generation_id, domain_label, nonsyn_count, syn_count,
             total_protein_mutations, domain_length, nonsyn_per_residue
      FROM mv_domain_mutation_enrichment
    """
    params = ()
    if generation_id is not None:
        sql += " WHERE generation_id = %s"
        params = (int(generation_id),)

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        raise RuntimeError(
            "No rows found in mv_domain_mutation_enrichment. "
            "Did you build/refresh the MV with valid protein_features (wt_id mapping)?"
        )

    if generation_id is not None:
        df = df.sort_values(metric, ascending=False).head(25)
        fig = px.bar(
            df,
            x=metric,
            y="domain_label",
            orientation="h",
            title=f"Domain Enrichment (Gen {generation_id})",
            hover_data=["domain_length", "syn_count", "total_protein_mutations"],
        )
        fig.update_layout(yaxis_title="Domain/Region", xaxis_title=metric)
        fig.write_html(str(out_path))
        return out_path

    heat = df.pivot_table(index="domain_label", columns="generation_id", values=metric, fill_value=0)
    fig = px.imshow(
        heat,
        aspect="auto",
        title=f"Domain-level Mutation Enrichment by Generation ({metric})",
        labels=dict(x="Generation", y="Domain/Region", color=metric),
    )
    fig.write_html(str(out_path))
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Plot domain-level mutation enrichment heatmap.")
    ap.add_argument("--generation-id", type=int, required=False, help="Optional: filter to one generation.")
    ap.add_argument("--metric", choices=["nonsyn_count", "nonsyn_per_residue"], default="nonsyn_count")
    ap.add_argument("--out", default="outputs/domain_enrichment_heatmap.html")
    args = ap.parse_args()

    out = plot_domain_enrichment(
        generation_id=args.generation_id,
        metric=args.metric,
        out_path=args.out,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()