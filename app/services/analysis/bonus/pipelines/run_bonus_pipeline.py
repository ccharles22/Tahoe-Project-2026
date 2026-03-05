"""Entry point for optional bonus-analysis generation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from app.services.analysis.bonus.database.postgres import get_cursor
from app.services.analysis.bonus.embeddings.precompute_embeddings import precompute_embeddings_for_generation

from app.services.analysis.bonus.visualisations.plot_activity_landscape import plot_activity_landscape_plotly
from app.services.analysis.bonus.visualisations.plot_activity_surface_matplotlib import plot_activity_surface_matplotlib
from app.services.analysis.bonus.visualisations.plot_mutation_frequency import plot_mutation_frequency
from app.services.analysis.bonus.visualisations.plot_mutation_fingerprint import (
    plot_mutation_fingerprint_dropdown,
)
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


def refresh_materialized_views(view_names: Sequence[str]) -> dict[str, str]:
    """Refresh named materialized views and report any failures by name."""
    failures: dict[str, str] = {}
    for v in view_names:
        try:
            with get_cursor(commit=True) as cur:
                cur.execute(f"REFRESH MATERIALIZED VIEW {v};")
        except Exception as exc:
            failures[v] = f"{type(exc).__name__}: {exc}"
    return failures


def _write_placeholder_html(out_path: Path, title: str, message: str) -> Path:
    """Write a small HTML placeholder so the bonus section remains populated."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped_message = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )
    out_path.write_text(
        f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{escaped_title}</title>
    <style>
      :root {{
        color-scheme: light;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 32px;
        font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #18324a;
        background:
          radial-gradient(circle at top right, rgba(208, 232, 255, 0.7), transparent 34%),
          linear-gradient(180deg, #f8fbff 0%, #eef5ff 100%);
      }}
      .placeholder {{
        width: min(100%, 760px);
        padding: 28px 30px;
        border-radius: 22px;
        border: 1px solid #d3e4f6;
        background: rgba(255, 255, 255, 0.92);
        box-shadow: 0 18px 38px rgba(12, 38, 66, 0.08);
      }}
      .eyebrow {{
        margin: 0 0 10px;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #3b82f6;
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: clamp(28px, 4vw, 44px);
        line-height: 1;
        font-family: Georgia, "Times New Roman", serif;
      }}
      p {{
        margin: 0;
        font-size: 15px;
        line-height: 1.7;
        color: #486178;
      }}
    </style>
  </head>
  <body>
    <section class="placeholder">
      <p class="eyebrow">Bonus visualisation unavailable</p>
      <h1>{escaped_title}</h1>
      <p>{escaped_message}</p>
    </section>
  </body>
</html>
""",
        encoding="utf-8",
    )
    return out_path


def activity_scores_available(generation_id: int) -> bool:
    """Return whether this generation has derived variant activity_score rows."""
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
    return n > 0


def get_top_variant_ids(generation_id: int, limit: int = 10) -> list[int]:
    """Return top-ranked variant_ids by activity_score for a generation."""
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
            ORDER BY m.value DESC, v.variant_id DESC
            LIMIT %s
            """,
            (generation_id, int(limit)),
        )
        return [int(row[0]) for row in cur.fetchall()]


def get_fallback_variant_id(generation_id: int) -> Optional[int]:
    """Pick a recent variant with the richest non-synonymous protein mutation signal."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH ranked AS (
                SELECT
                  v.variant_id,
                  COUNT(*) FILTER (
                    WHERE m.mutation_type = 'protein'
                      AND (m.is_synonymous IS FALSE OR m.is_synonymous IS NULL)
                  ) AS nonsyn_mutations
                FROM variants v
                LEFT JOIN mutations m ON m.variant_id = v.variant_id
                WHERE v.generation_id = %s
                GROUP BY v.variant_id
            )
            SELECT variant_id
            FROM ranked
            ORDER BY nonsyn_mutations DESC, variant_id DESC
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
    """Run the full bonus-analysis pipeline for one generation."""
    outputs_dir.mkdir(parents=True, exist_ok=True)
    generated_count = 0
    failures: list[str] = []

    def _run_plot(
        label: str,
        func,
        *args,
        placeholder_title: Optional[str] = None,
        placeholder_message: Optional[str] = None,
        **kwargs,
    ):
        nonlocal generated_count
        out_path = kwargs.get("out_path")
        try:
            out = func(*args, **kwargs)
            generated_count += 1
            return out
        except Exception as exc:
            failures.append(f"{label}: {type(exc).__name__}: {exc}")
            print(f"[warn] {label} skipped: {type(exc).__name__}: {exc}")
            if (
                out_path is not None
                and isinstance(out_path, Path)
                and out_path.suffix.lower() == ".html"
                and placeholder_title
            ):
                placeholder = _write_placeholder_html(
                    out_path,
                    placeholder_title,
                    placeholder_message or f"This view could not be generated: {type(exc).__name__}: {exc}",
                )
                generated_count += 1
                return placeholder
            return None

    def _skip_plot(label: str, reason: str, *, out_path: Optional[Path] = None, placeholder_title: Optional[str] = None):
        nonlocal generated_count
        failures.append(f"{label}: {reason}")
        print(f"[warn] {label} skipped: {reason}")
        if out_path is not None and out_path.suffix.lower() == ".html" and placeholder_title:
            placeholder = _write_placeholder_html(out_path, placeholder_title, reason)
            generated_count += 1
            return placeholder
        return None

    # Preconditions
    has_activity_scores = activity_scores_available(generation_id)

    # If user requests tsne landscape, ensure we computed tsne coords
    if landscape_method == "tsne" and not include_tsne:
        raise SystemExit(
            "You selected --landscape-method tsne but did not pass --include-tsne.\n"
            "Run again with: --include-tsne"
        )

    if has_activity_scores:
        # Ensure metric definitions exist only when embeddings are needed.
        ensure_metric_definitions()

        # Precompute PCA/t-SNE embeddings into metrics.
        precompute_embeddings_for_generation(
            generation_id=generation_id,
            include_tsne=include_tsne,
            seed=seed,
            perplexity=perplexity,
            refresh_view=False,
        )
        
        # Refresh domain enrichment view after embeddings are computed
        mv_failures = refresh_materialized_views(["mv_domain_mutation_enrichment"])
        for view, error in mv_failures.items():
            print(f"[warn] Failed to refresh {view}: {error}")
    else:
        print(
            f"[warn] No activity_score metrics found for generation_id={generation_id}. "
            "Skipping activity-dependent bonus plots."
        )

    # ---- Plots ----

    if has_activity_scores:
        out_landscape = _run_plot(
            "Landscape (Plotly)",
            plot_activity_landscape_plotly,
            generation_id=generation_id,
            method=landscape_method,
            mode=landscape_mode,
            grid_size=grid_size,
            out_path=outputs_dir / f"activity_landscape_{landscape_method}_{landscape_mode}.html",
            placeholder_title="Activity Landscape",
            placeholder_message="This generation does not yet have enough valid embedding and activity data to render the landscape.",
        )

        out_surface = _run_plot(
            "Surface (Matplotlib)",
            plot_activity_surface_matplotlib,
            generation_id=generation_id,
            method=landscape_method,
            grid_size=grid_size,
            out_path=outputs_dir / f"activity_surface_{landscape_method}.png",
        )

        out_traj = _run_plot(
            "Trajectory",
            plot_mutation_trajectory,
            generation_id=generation_id,
            top_n=top_n,
            out_path=outputs_dir / f"mutation_trajectory_top{top_n}.html",
            placeholder_title="Mutation Trajectory",
            placeholder_message="The latest generation does not yet have enough ranked variants to build a mutation trajectory.",
        )
    else:
        out_landscape = _skip_plot(
            "Landscape (Plotly)",
            "No activity_score metrics found for this generation.",
            out_path=outputs_dir / f"activity_landscape_{landscape_method}_{landscape_mode}.html",
            placeholder_title="Activity Landscape",
        )
        out_surface = _skip_plot("Surface (Matplotlib)", "No activity_score metrics found for this generation.")
        out_traj = _skip_plot(
            "Trajectory",
            "No activity_score metrics found for this generation.",
            out_path=outputs_dir / f"mutation_trajectory_top{top_n}.html",
            placeholder_title="Mutation Trajectory",
        )

    # All-generation heatmap
    out_domain_heat = _run_plot(
        "Domain heatmap",
        plot_domain_enrichment,
        generation_id=None,
        metric="nonsyn_count",
        out_path=outputs_dir / "domain_enrichment_heatmap.html",
        placeholder_title="Domain Heatmap",
        placeholder_message="Domain enrichment could not be computed for this experiment because the required domain annotations or protein mutation data are missing.",
    )

    out_mutation_frequency = _run_plot(
        "Mutation frequency",
        plot_mutation_frequency,
        generation_id=None,
        out_path=outputs_dir / "mutation_frequency_by_position.html",
        placeholder_title="Mutation Frequency",
        placeholder_message="No non-synonymous protein mutations are available yet for this experiment, so mutation frequency cannot be shown.",
    )

    # Build fingerprint selector from top-ranked variants.
    fingerprint_variant_ids: list[int] = []
    if has_activity_scores:
        fingerprint_variant_ids = get_top_variant_ids(generation_id, limit=10)

    # Allow explicit override with a specific variant.
    if fingerprint_variant_id is not None:
        fingerprint_variant_ids = [int(fingerprint_variant_id)]

    # Fallback to a single best-available variant if ranking data is missing.
    if not fingerprint_variant_ids:
        fallback_vid = get_fallback_variant_id(generation_id)
        if fallback_vid is not None:
            fingerprint_variant_ids = [fallback_vid]

    out_fingerprint = None
    if fingerprint_variant_ids:
        out_fingerprint = _run_plot(
            "Fingerprint",
            plot_mutation_fingerprint_dropdown,
            variant_ids=fingerprint_variant_ids,
            out_path=outputs_dir / "mutation_fingerprint_latest.html",
            placeholder_title="Mutation Fingerprint",
            placeholder_message="A mutation fingerprint could not be built for the top-ranked variants.",
        )
    else:
        out_fingerprint = _skip_plot(
            "Fingerprint",
            "No suitable variant with mutation data is available for the latest generation.",
            out_path=outputs_dir / "mutation_fingerprint_latest.html",
            placeholder_title="Mutation Fingerprint",
        )

    if generated_count == 0:
        details = "; ".join(failures) if failures else "No bonus outputs were written."
        raise SystemExit(
            f"No bonus visualisations were generated for generation_id={generation_id}. {details}"
        )

    print("\n Bonus visualisation pipeline complete.")
    print(f"Outputs directory: {outputs_dir.resolve()}")
    print(f"- Landscape (Plotly): {out_landscape}")
    print(f"- Surface (Matplotlib): {out_surface}")
    print(f"- Trajectory: {out_traj}")
    print(f"- Domain heatmap: {out_domain_heat}")
    print(f"- Mutation frequency: {out_mutation_frequency}")
    if out_fingerprint:
        print(f"- Fingerprint: {out_fingerprint}")
    else:
        print("- Fingerprint: skipped (no top variant found)")
    if failures:
        print("- Some bonus visualisations were skipped:")
        for failure in failures:
            print(f"  * {failure}")


def main():
    """CLI entrypoint for the end-to-end bonus-analysis pipeline."""
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
