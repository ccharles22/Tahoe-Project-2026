from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from app.services.analysis.bonus.database.postgres import get_cursor
from app.services.analysis.bonus.embeddings.precompute_embeddings import precompute_embeddings_for_generation

from app.services.analysis.bonus.visualisations.plot_activity_landscape import plot_activity_landscape_plotly
from app.services.analysis.bonus.visualisations.plot_activity_surface_matplotlib import plot_activity_surface_matplotlib
from app.services.analysis.bonus.visualisations.plot_mutation_fingerprint import plot_mutation_fingerprint
from app.services.analysis.bonus.visualisations.plot_mutation_trajectory import plot_mutation_trajectory
from app.services.analysis.bonus.visualisations.plot_domain_enrichment import plot_domain_enrichment


# -----------
# SQL helpers
# -----------

def _read_sql_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    return path.read_text(encoding="utf-8")


def _strip_sql_comments(sql: str) -> str:
    """Strip '--' line comments to avoid breaking semicolon-based statement splitting."""
    lines = []
    for line in sql.splitlines():
        # Keep anything before '--'
        if "--" in line:
            line = line.split("--", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def _exec_sql(conn_cursor, sql: str) -> None:
    """Runs multi-statement SQL by splitting on semicolons."""
    sql = _strip_sql_comments(sql)
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        conn_cursor.execute(stmt + ";")


def ensure_metric_definitions() -> None:
    """Idempotent insert of PCA/t-SNE metric definitions."""
    with get_cursor(commit=True) as cur:
        for name, desc in [
            ("pca_x", "PCA embedding X coordinate (mutation-vector)"),
            ("pca_y", "PCA embedding Y coordinate (mutation-vector)"),
            ("tsne_x", "t-SNE embedding X coordinate (mutation-vector)"),
            ("tsne_y", "t-SNE embedding Y coordinate (mutation-vector)"),
        ]:
            cur.execute(
                """
                INSERT INTO metric_definitions (name, description, unit, metric_type)
                SELECT %s, %s, NULL, 'derived'
                WHERE NOT EXISTS (
                  SELECT 1 FROM metric_definitions WHERE name=%s AND metric_type='derived'
                )
                """,
                (name, desc, name),
            )


def ensure_materialized_views(sql_dir: Path) -> None:
    """
    Expected SQL files:
      sql/views/mv_activity_landscape.sql
      sql/views/mv_domain_mutation_enrichment.sql
    """
    mv1_path = sql_dir / "views" / "mv_activity_landscape.sql"
    mv2_path = sql_dir / "views" / "mv_domain_mutation_enrichment.sql"

    mv1 = _read_sql_file(mv1_path)
    mv2 = _read_sql_file(mv2_path)

    with get_cursor(commit=True) as cur:
        _exec_sql(cur, mv1)
        _exec_sql(cur, mv2)


def refresh_materialized_views(view_names: Sequence[str]) -> None:
    with get_cursor(commit=True) as cur:
        for v in view_names:
            cur.execute(f"REFRESH MATERIALIZED VIEW {v};")


def check_activity_score_exists(generation_id: int) -> None:
    """Fails early if a teammate's activity_score pipeline hasn't run yet."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM metrics
            WHERE generation_id=%s
              AND metric_name='activity_score'
              AND metric_type='derived'
              AND variant_id IS NOT NULL
            """,
            (generation_id,),
        )
        n = int(cur.fetchone()[0])

    if n == 0:
        raise SystemExit(
            f"No activity_score metrics found for generation_id={generation_id}.\n"
            "Run the activity score computation first (your teammate's stage), then rerun this pipeline."
        )


def get_top_variant_id(generation_id: int) -> Optional[int]:
    """Picks the highest-activity variant for fingerprinting."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT v.variant_id
            FROM variants v
            JOIN metrics m
              ON m.variant_id=v.variant_id
             AND m.generation_id=v.generation_id
             AND m.metric_name='activity_score'
             AND m.metric_type='derived'
            WHERE v.generation_id=%s
            ORDER BY m.value DESC
            LIMIT 1
            """,
            (generation_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else None


# -----------------------------
# Main pipeline
# -----------------------------

def run_pipeline(
    generation_id: int,
    sql_dir: Path,
    outputs_dir: Path,
    include_tsne: bool,
    perplexity: int,
    seed: int,
    landscape_method: str,
    landscape_mode: str,
    grid_size: int,
    top_n: int,
    fingerprint_variant_id: Optional[int],
    skip_create_views: bool,
) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Preconditions
    check_activity_score_exists(generation_id)

    # If user requests tsne landscape, ensure we computed tsne coords
    if landscape_method == "tsne" and not include_tsne:
        raise SystemExit(
            "You selected --landscape-method tsne but did not pass --include-tsne.\n"
            "Run again with: --include-tsne"
        )

    # Ensure metric definitions exist
    ensure_metric_definitions()

    # Create views (optional) and refresh
    if not skip_create_views:
        ensure_materialized_views(sql_dir)

    # Precompute PCA/t-SNE embeddings into metrics
    precompute_embeddings_for_generation(
        generation_id=generation_id,
        include_tsne=include_tsne,
        seed=seed,
        perplexity=perplexity,
        refresh_view=False,
    )

    # Refresh datatables
    refresh_materialized_views(["mv_activity_landscape", "mv_domain_mutation_enrichment"])

    # ---- Plots ----

    out_landscape = plot_activity_landscape_plotly(
        generation_id=generation_id,
        method=landscape_method,
        mode=landscape_mode,
        grid_size=grid_size,
        out_path=outputs_dir / f"activity_landscape_{landscape_method}_{landscape_mode}.html",
    )

    out_surface = plot_activity_surface_matplotlib(
        generation_id=generation_id,
        method=landscape_method,
        grid_size=grid_size,
        out_path=outputs_dir / f"activity_surface_{landscape_method}.png",
    )

    out_traj = plot_mutation_trajectory(
        generation_id=generation_id,
        top_n=top_n,
        out_path=outputs_dir / f"mutation_trajectory_top{top_n}.html",
    )

    # All-generation heatmap
    out_domain_heat = plot_domain_enrichment(
        generation_id=None,
        metric="nonsyn_count",
        out_path=outputs_dir / "domain_enrichment_heatmap.html",
    )

    # Single-generation bar chart
    out_domain_bar = plot_domain_enrichment(
        generation_id=generation_id,
        metric="nonsyn_count",
        out_path=outputs_dir / f"domain_enrichment_gen{generation_id}.html",
    )

    # Use top-activity variant if none specified
    vid = fingerprint_variant_id or get_top_variant_id(generation_id)
    out_fingerprint = None
    if vid is not None:
        out_fingerprint = plot_mutation_fingerprint(
            variant_id=vid,
            out_path=outputs_dir / f"mutation_fingerprint_variant{vid}.html",
        )

    print("\n Bonus visualisation pipeline complete.")
    print(f"Outputs directory: {outputs_dir.resolve()}")
    print(f"- Landscape (Plotly): {out_landscape}")
    print(f"- Surface (Matplotlib): {out_surface}")
    print(f"- Trajectory: {out_traj}")
    print(f"- Domain heatmap: {out_domain_heat}")
    print(f"- Domain (gen bar): {out_domain_bar}")
    if out_fingerprint:
        print(f"- Fingerprint: {out_fingerprint}")
    else:
        print("- Fingerprint: skipped (no top variant found)")


def main():
    ap = argparse.ArgumentParser(
        description="Run complete bonus visualisation pipeline: embeddings + views + plots."
    )

    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--sql-dir", type=str, default="sql")
    ap.add_argument("--outputs-dir", type=str, default="outputs")

    ap.add_argument("--include-tsne", action="store_true")
    ap.add_argument("--perplexity", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)

    ap.add_argument("--landscape-method", choices=["pca", "tsne"], default="pca")
    ap.add_argument("--landscape-mode", choices=["scatter", "surface"], default="scatter")
    ap.add_argument("--grid-size", type=int, default=60)

    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--fingerprint-variant-id", type=int, default=None)

    ap.add_argument(
        "--skip-create-views",
        action="store_true",
        help="Use if MVs already exist in the DataBase; pipeline will only refresh them.",
    )

    args = ap.parse_args()

    run_pipeline(
        generation_id=args.generation_id,
        sql_dir=Path(args.sql_dir),
        outputs_dir=Path(args.outputs_dir),
        include_tsne=args.include_tsne,
        perplexity=args.perplexity,
        seed=args.seed,
        landscape_method=args.landscape_method,
        landscape_mode=args.landscape_mode,
        grid_size=args.grid_size,
        top_n=args.top_n,
        fingerprint_variant_id=args.fingerprint_variant_id,
        skip_create_views=args.skip_create_views,
    )


if __name__ == "__main__":
    main()