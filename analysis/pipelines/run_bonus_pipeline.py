from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional, Sequence

from analysis.database.postgres import get_cursor
from analysis.embeddings.precompute_embeddings import precompute_embeddings_for_generation

from visualisations.plot_activity_landscape import plot_activity_landscape_plotly
from visualisations.plot_mutation_fingerprint import plot_mutation_fingerprint_dropdown
from visualisations.plot_domain_enrichment import plot_domain_enrichment
from visualisations.plot_mutation_frequency import plot_mutation_frequency


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


def _mv_has_columns(cur, view_name: str, required_cols: Sequence[str]) -> bool:
    """Check whether a materialized view already contains all *required_cols*.

    Uses pg_attribute + pg_class because information_schema.columns does NOT
    include materialized views in PostgreSQL.
    """
    cur.execute(
        """
        SELECT a.attname
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relname = %s
          AND c.relkind = 'm'
          AND a.attnum > 0
          AND NOT a.attisdropped
        """,
        (view_name,),
    )
    existing = {row[0] for row in cur.fetchall()}
    if not existing:
        # View doesn't exist at all — let CREATE IF NOT EXISTS handle it
        return True
    return all(c in existing for c in required_cols)


def ensure_materialized_views(sql_dir: Path) -> None:
    """
    Expected SQL files:
      sql/views/mv_activity_landscape.sql
      sql/views/mv_domain_mutation_enrichment.sql

    If views exist with the correct schema, this is a no-op (CREATE IF NOT EXISTS).
    If views exist but are missing expected columns, raise a clear error
    asking the DB owner to recreate them (requires CREATE privilege).
    """
    mv1_path = sql_dir / "views" / "mv_activity_landscape.sql"
    mv2_path = sql_dir / "views" / "mv_domain_mutation_enrichment.sql"

    mv1 = _read_sql_file(mv1_path)
    mv2 = _read_sql_file(mv2_path)

    with get_cursor(commit=True) as cur:
        stale = []
        if not _mv_has_columns(cur, "mv_activity_landscape", ["x", "y", "method", "activity_score"]):
            stale.append("mv_activity_landscape")
        if not _mv_has_columns(cur, "mv_domain_mutation_enrichment", ["nonsyn_per_residue"]):
            stale.append("mv_domain_mutation_enrichment")

        if stale:
            names = ", ".join(stale)
            raise RuntimeError(
                f"Materialized view(s) [{names}] exist but have an outdated schema "
                f"(missing required columns).\n"
                f"Ask the DB owner to run:\n"
                + "\n".join(f"  DROP MATERIALIZED VIEW IF EXISTS {v};" for v in stale)
                + "\nThen re-run this pipeline to recreate them."
            )

        try:
            _exec_sql(cur, mv1)
            _exec_sql(cur, mv2)
        except Exception as e:
            if "permission denied" in str(e).lower():
                raise RuntimeError(
                    "Cannot create materialized views (no CREATE privilege on schema).\n"
                    "If the views already exist, re-run with --skip-create-views."
                ) from e
            raise


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


def get_top_variant_ids(generation_id: Optional[int] = None, limit: int = 10) -> List[int]:
    """Return up to *limit* highest-activity variant IDs that have
    non-synonymous protein mutations in the mutations table.

    Prefers variants with the deepest lineage chains (most ancestor
    generations) so the fingerprint plots display mutations accumulated
    across many generations rather than only the final one.

    If *generation_id* is supplied, only that generation is searched.
    """
    with get_cursor() as cur:
        if generation_id is not None:
            cur.execute(
                """
                SELECT v.variant_id
                FROM variants v
                JOIN metrics m
                  ON m.variant_id = v.variant_id
                 AND m.generation_id = v.generation_id
                 AND m.metric_name  = 'activity_score'
                 AND m.metric_type  = 'derived'
                WHERE v.generation_id = %s
                  AND EXISTS (
                      SELECT 1
                      FROM mutations mu
                      WHERE mu.variant_id = v.variant_id
                        AND mu.mutation_type = 'protein'
                        AND (mu.is_synonymous IS FALSE OR mu.is_synonymous IS NULL)
                  )
                ORDER BY m.value DESC
                LIMIT %s
                """,
                (generation_id, limit),
            )
            ids = [int(r[0]) for r in cur.fetchall()]
            if ids:
                return ids

        cur.execute(
            """
            WITH lineage_depth AS (
                -- Recursive CTE to measure each variant's lineage depth
                WITH RECURSIVE chain AS (
                    SELECT v.variant_id, v.parent_variant_id, 0 AS depth
                    FROM variants v
                    UNION ALL
                    SELECT c.variant_id, p.parent_variant_id, c.depth + 1
                    FROM chain c
                    JOIN variants p ON p.variant_id = c.parent_variant_id
                    WHERE c.parent_variant_id IS NOT NULL
                )
                SELECT variant_id, MAX(depth) AS max_depth
                FROM chain
                GROUP BY variant_id
            )
            SELECT v.variant_id
            FROM variants v
            JOIN metrics m
              ON m.variant_id = v.variant_id
             AND m.generation_id = v.generation_id
             AND m.metric_name  = 'activity_score'
             AND m.metric_type  = 'derived'
            JOIN lineage_depth ld
              ON ld.variant_id = v.variant_id
            WHERE ld.max_depth >= 5  -- at least 5 generations of ancestors
              AND EXISTS (
                  SELECT 1
                  FROM mutations mu
                  WHERE mu.variant_id = v.variant_id
                    AND mu.mutation_type = 'protein'
                    AND (mu.is_synonymous IS FALSE OR mu.is_synonymous IS NULL)
              )
            ORDER BY m.value DESC
            LIMIT %s
            """,
            (limit,),
        )
        ids = [int(r[0]) for r in cur.fetchall()]
        if ids:
            return ids

        # Fallback: any variant with mutations, ordered by activity
        cur.execute(
            """
            SELECT v.variant_id
            FROM variants v
            JOIN metrics m
              ON m.variant_id = v.variant_id
             AND m.generation_id = v.generation_id
             AND m.metric_name  = 'activity_score'
             AND m.metric_type  = 'derived'
            WHERE EXISTS (
                  SELECT 1
                  FROM mutations mu
                  WHERE mu.variant_id = v.variant_id
                    AND mu.mutation_type = 'protein'
                    AND (mu.is_synonymous IS FALSE OR mu.is_synonymous IS NULL)
              )
            ORDER BY m.value DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [int(r[0]) for r in cur.fetchall()]


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
    fingerprint_variant_id: Optional[int],
    skip_create_views: bool,
    skip_refresh_views: bool = False,
) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)

    check_activity_score_exists(generation_id)

    if landscape_method == "tsne" and not include_tsne:
        raise SystemExit(
            "You selected --landscape-method tsne but did not pass --include-tsne.\n"
            "Run again with: --include-tsne"
        )

    ensure_metric_definitions()

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
    if not skip_refresh_views:
        refresh_materialized_views(["mv_activity_landscape", "mv_domain_mutation_enrichment"])
    else:
        print("Skipping materialized view refresh (--skip-refresh-views).")

    # ---- Plots ----
    # All-generations landscape (entire dataset)
    out_landscape_all = plot_activity_landscape_plotly(
        generation_id=None,
        method=landscape_method,
        mode=landscape_mode,
        grid_size=grid_size,
        out_path=outputs_dir / f"activity_landscape_{landscape_method}_{landscape_mode}_all_gens.html",
    )

    # All-generation heatmap
    out_domain_heat = plot_domain_enrichment(
        generation_id=None,
        metric="nonsyn_count",
        out_path=outputs_dir / "domain_enrichment_heatmap.html",
    )

    # ---- Mutation fingerprint (interactive dropdown selector) ----
    if fingerprint_variant_id:
        fp_variant_ids = [fingerprint_variant_id]
    else:
        fp_variant_ids = get_top_variant_ids(generation_id=None, limit=10)

    out_fingerprint_dropdown = plot_mutation_fingerprint_dropdown(
        variant_ids=fp_variant_ids,
        out_path=outputs_dir / "mutation_fingerprint_selector.html",
    )

    # Mutation frequency by position (hotspot analysis)
    out_freq = plot_mutation_frequency(
        out_path=outputs_dir / "mutation_frequency_by_position.html",
    )

    print("\n Bonus visualisation pipeline complete.")
    print(f"Outputs directory: {outputs_dir.resolve()}")
    print(f"- Landscape (Plotly, All Gens): {out_landscape_all}")
    print(f"- Domain heatmap: {out_domain_heat}")
    print(f"- Mutation frequency: {out_freq}")
    if out_fingerprint_dropdown:
        print(f"- Fingerprint (selector): {out_fingerprint_dropdown}")
    else:
        print("- Fingerprint selector: skipped (no suitable variants found)")


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
    ap.add_argument("--landscape-mode", choices=["scatter", "surface"], default="surface")
    ap.add_argument("--grid-size", type=int, default=60)

    ap.add_argument("--fingerprint-variant-id", type=int, default=None)

    ap.add_argument(
        "--skip-create-views",
        action="store_true",
        help="Use if MVs already exist in the DataBase; pipeline will only refresh them.",
    )
    ap.add_argument(
        "--skip-refresh-views",
        action="store_true",
        help="Skip REFRESH MATERIALIZED VIEW (use when your DB role lacks refresh privileges).",
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
        fingerprint_variant_id=args.fingerprint_variant_id,
        skip_create_views=args.skip_create_views,
        skip_refresh_views=args.skip_refresh_views,
    )


if __name__ == "__main__":
    main()