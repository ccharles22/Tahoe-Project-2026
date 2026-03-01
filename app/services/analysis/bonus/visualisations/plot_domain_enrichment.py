from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal, Optional

import pandas as pd
import plotly.express as px

from app.services.analysis.bonus.database.postgres import get_connection


def plot_domain_enrichment(
    generation_id: Optional[int] = None,
    metric: Literal["nonsyn_count", "nonsyn_per_residue"] = "nonsyn_count",
    single_generation: bool = False,
    out_path: Path | str = "outputs/domain_enrichment_heatmap.html",
) -> Path:
    """Bar chart for a single generation, or cross-generation heatmap when generation_id is None."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if generation_id is None:
        raise ValueError("generation_id is required to resolve the target experiment.")

    sql = """
      WITH target_experiment AS (
        SELECT e.experiment_id, e.wt_id
        FROM generations g
        JOIN experiments e ON e.experiment_id = g.experiment_id
        WHERE g.generation_id = %s
        LIMIT 1
      )
      SELECT
        v.generation_id,
        MIN(COALESCE(pf.description, pf.feature_type)) AS domain_label,
        COUNT(*) FILTER (WHERE m.is_synonymous IS FALSE) AS nonsyn_count,
        COUNT(*) FILTER (WHERE m.is_synonymous IS TRUE) AS syn_count,
        COUNT(*) AS total_protein_mutations,
        (pf.end_position - pf.start_position + 1) AS domain_length,
        COUNT(*) FILTER (WHERE m.is_synonymous IS FALSE)::float
          / NULLIF((pf.end_position - pf.start_position + 1), 0) AS nonsyn_per_residue
      FROM target_experiment te
      JOIN generations g
        ON g.experiment_id = te.experiment_id
      JOIN variants v
        ON v.generation_id = g.generation_id
      JOIN mutations m
        ON m.variant_id = v.variant_id
       AND m.mutation_type = 'protein'
      JOIN protein_features pf
        ON pf.wt_id = te.wt_id
       AND m.position BETWEEN pf.start_position AND pf.end_position
      WHERE (%s IS FALSE OR v.generation_id = %s)
      GROUP BY
        v.generation_id,
        pf.feature_type,
        pf.start_position,
        pf.end_position
    """
    params = (int(generation_id), single_generation, int(generation_id))

    with get_connection() as conn:
        df = pd.read_sql_query(sql, conn, params=params)

    if df.empty:
        raise RuntimeError(
            "No domain-linked protein mutations were found for this experiment. "
            "Domain enrichment requires both protein features and protein mutation rows."
        )

    if single_generation:
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
