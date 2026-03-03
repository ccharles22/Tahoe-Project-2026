from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.services.analysis.activity_score import compute_stage4_metrics
from app.services.analysis.database import get_conn
from app.services.analysis.metrics import upsert_variant_metrics
from app.services.analysis.plots.distribution import plot_activity_distribution
from app.services.analysis.plots.lineage import PlotConfig, plot_layered_lineage
from app.services.analysis.plots.protein_similarity_network import (
    ProteinNetConfig,
    plot_protein_similarity_network,
)
from app.services.analysis.plots.top10 import plot_top10_table
from app.services.analysis.queries import (
    fetch_distribution,
    fetch_lineage_edges,
    fetch_lineage_nodes,
    fetch_protein_similarity_nodes,
    fetch_protein_mutations,
    fetch_top10,
    fetch_variant_raw,
    fetch_wt_baselines,
)

OUTPUT_DIR = Path("app/static/generated")
SCORE_TOL = 1e-9


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def db_count_activity_scores(conn, experiment_id: int) -> tuple[int, int]:
    """Returns (all_activity_scores, this_experiment_activity_scores)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM metrics
            WHERE metric_name='activity_score'
              AND metric_type='derived'
              AND variant_id IS NOT NULL;
            """
        )
        all_n = int(cur.fetchone()[0])

        cur.execute(
            """
            SELECT COUNT(*)
            FROM metrics m
            JOIN variants v ON v.variant_id = m.variant_id
            JOIN generations g ON g.generation_id = v.generation_id
            WHERE m.metric_name='activity_score'
              AND m.metric_type='derived'
              AND g.experiment_id = %s;
            """,
            (experiment_id,),
        )
        exp_n = int(cur.fetchone()[0])

    return all_n, exp_n


def _sequence_state(experiment_id: int) -> dict[str, Any]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              e.analysis_status,
              COUNT(v.variant_id) AS variant_count,
              COUNT(vsa.vsa_id) AS vsa_rows,
              COUNT(*) FILTER (
                WHERE v.variant_id IS NOT NULL
                  AND NULLIF(BTRIM(COALESCE(v.protein_sequence, '')), '') IS NOT NULL
              ) AS protein_ready_count
            FROM public.experiments e
            LEFT JOIN public.generations g
              ON g.experiment_id = e.experiment_id
            LEFT JOIN public.variants v
              ON v.generation_id = g.generation_id
            LEFT JOIN public.variant_sequence_analysis vsa
              ON vsa.variant_id = v.variant_id
             AND vsa.analysis_version = 'v1'
            WHERE e.experiment_id = %s
            GROUP BY e.analysis_status
            """,
            (experiment_id,),
        )
        row = cur.fetchone()

    if row is None:
        raise SystemExit(f"[Sequence] Experiment {experiment_id} not found.")

    return {
        "analysis_status": row[0],
        "variant_count": int(row[1] or 0),
        "vsa_rows": int(row[2] or 0),
        "protein_ready_count": int(row[3] or 0),
    }


def _needs_sequence_backfill(state: dict[str, Any], *, force: bool) -> bool:
    if force:
        return True

    if state["variant_count"] == 0:
        return False

    if state["analysis_status"] in {None, "FAILED"}:
        return True

    if state["vsa_rows"] < state["variant_count"]:
        return True

    if state["protein_ready_count"] == 0:
        return True

    return False


def _run_sequence_processing(experiment_id: int) -> None:
    worktree = Path(
        os.getenv("SEQUENCE_PROCESSING_WORKTREE", "/tmp/ui_test_worktree")
    )
    if not worktree.exists():
        raise SystemExit(
            "[Sequence] UI_test worktree not found at "
            f"{worktree}. Set SEQUENCE_PROCESSING_WORKTREE to the correct path."
        )

    env = os.environ.copy()
    env.setdefault("FALLBACK_SEARCH", "true")
    env.setdefault("PYTHONUNBUFFERED", "1")

    python_exe = os.getenv("SEQUENCE_PROCESSING_PYTHON", sys.executable)
    cmd = [
        python_exe,
        "-c",
        (
            "import logging; "
            "logging.basicConfig(level=logging.INFO, "
            "format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'); "
            "from app.jobs.run_sequence_processing import run_sequence_processing; "
            f"run_sequence_processing({experiment_id}, force_reprocess=True)"
        ),
    ]

    print(
        "[Sequence] Running UI_test sequence processing first "
        f"(experiment {experiment_id})..."
    )
    subprocess.run(cmd, cwd=worktree, env=env, check=True)


def ensure_sequence_processing_ready(experiment_id: int) -> None:
    auto_run = _env_bool("AUTO_RUN_SEQUENCE_PROCESSING", True)
    force_run = _env_bool("FORCE_SEQUENCE_PROCESSING", False)

    state = _sequence_state(experiment_id)
    if state["analysis_status"] == "ANALYSIS_RUNNING":
        raise SystemExit(
            "[Sequence] Sequence processing is already running for "
            f"experiment {experiment_id}. Wait for it to finish before "
            "running the report."
        )

    if not _needs_sequence_backfill(state, force=force_run):
        print(
            "[Sequence] Existing sequence outputs look usable; "
            "skipping pre-run."
        )
        return

    if not auto_run and not force_run:
        raise SystemExit(
            "[Sequence] Sequence outputs are missing or incomplete for "
            f"experiment {experiment_id}. Re-run with "
            "AUTO_RUN_SEQUENCE_PROCESSING=true or run UI_test sequence "
            "processing manually first."
        )

    _run_sequence_processing(experiment_id)

    refreshed = _sequence_state(experiment_id)
    if _needs_sequence_backfill(refreshed, force=False):
        raise SystemExit(
            "[Sequence] Sequence processing finished, but outputs still look "
            f"incomplete for experiment {experiment_id}: {refreshed}"
        )

    print(
        "[Sequence] Sequence outputs are ready: "
        f"{refreshed['vsa_rows']}/{refreshed['variant_count']} analysed, "
        f"{refreshed['protein_ready_count']} proteins available."
    )


def _validate_stage4_formula(df_with_qc: pd.DataFrame) -> None:
    """Hard check: activity_score must equal dna_norm / protein_norm for all OK rows."""
    if "qc_stage4" not in df_with_qc.columns:
        raise ValueError("Stage4 validation failed: qc_stage4 column missing.")

    ok = df_with_qc[df_with_qc["qc_stage4"] == "ok"].copy()
    if ok.empty:
        raise ValueError("Stage4 validation failed: no rows with qc_stage4='ok'.")

    required = {"dna_yield_norm", "protein_yield_norm", "activity_score"}
    if not required.issubset(ok.columns):
        missing = sorted(required - set(ok.columns))
        raise ValueError(f"Stage4 validation failed: missing columns {missing}.")

    calc = ok["dna_yield_norm"] / ok["protein_yield_norm"]
    err = (calc - ok["activity_score"]).abs()
    max_err = float(err.max())
    if not np.isfinite(max_err) or max_err > SCORE_TOL:
        raise ValueError(
            f"Stage4 validation failed: activity_score mismatch. max_abs_err={max_err:.3e}"
        )


def _validate_top10_consistency(df_with_qc: pd.DataFrame, df_top10: pd.DataFrame) -> None:
    """Hard check: top10 table must match highest activity_score values from stage4 outputs."""
    required_top10 = {"generation_number", "plasmid_variant_index", "activity_score", "total_mutations"}
    if not required_top10.issubset(df_top10.columns):
        missing = sorted(required_top10 - set(df_top10.columns))
        raise ValueError(f"Top10 validation failed: missing expected columns {missing}.")

    ok = df_with_qc[df_with_qc["qc_stage4"] == "ok"].copy()
    if ok.empty:
        raise ValueError("Top10 validation failed: no valid stage4 rows.")

    expect = (
        ok[["generation_number", "plasmid_variant_index", "activity_score"]]
        .sort_values("activity_score", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )
    actual = (
        df_top10[["generation_number", "plasmid_variant_index", "activity_score"]]
        .head(10)
        .reset_index(drop=True)
    )
    if len(expect) != len(actual):
        raise ValueError(
            f"Top10 validation failed: expected {len(expect)} rows, got {len(actual)}."
        )

    # Compare with tolerance for floating-point.
    same_gen = (expect["generation_number"].astype(str) == actual["generation_number"].astype(str)).all()
    same_idx = (expect["plasmid_variant_index"].astype(str) == actual["plasmid_variant_index"].astype(str)).all()
    score_err = (expect["activity_score"].astype(float) - actual["activity_score"].astype(float)).abs()
    same_score = bool((score_err <= SCORE_TOL).all())

    if not (same_gen and same_idx and same_score):
        raise ValueError("Top10 validation failed: table rows do not match highest activity scores.")


def compute_activity_score_fallback(
    df_variants: pd.DataFrame,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """
    WT-free scoring fallback:
    - Within each generation, normalise DNA and protein yields by generation median
    - activity_score = dna_norm / protein_norm

    Returns:
      rows_to_insert: list of metric rows suitable for upsert_variant_metrics (3 per OK variant)
      df_with_qc: df_variants with computed columns and qc_stage4 labels
    """
    d = df_variants.copy()

    required = {"variant_id", "generation_id", "dna_yield_raw", "protein_yield_raw"}
    missing = required - set(d.columns)
    if missing:
        raise ValueError(
            f"Fallback scoring requires columns {sorted(required)}; missing {sorted(missing)}"
        )

    d["dna_yield_raw"] = pd.to_numeric(d["dna_yield_raw"], errors="coerce")
    d["protein_yield_raw"] = pd.to_numeric(d["protein_yield_raw"], errors="coerce")

    d["dna_med"] = d.groupby("generation_id")["dna_yield_raw"].transform("median")
    d["prot_med"] = d.groupby("generation_id")["protein_yield_raw"].transform("median")

    d.loc[d["dna_med"] == 0, "dna_med"] = np.nan
    d.loc[d["prot_med"] == 0, "prot_med"] = np.nan

    d["dna_yield_norm"] = d["dna_yield_raw"] / d["dna_med"]
    d["protein_yield_norm"] = d["protein_yield_raw"] / d["prot_med"]
    d["activity_score"] = d["dna_yield_norm"] / d["protein_yield_norm"]

    d["qc_stage4"] = "ok"
    bad_mask = (
        d["variant_id"].isna()
        | d["generation_id"].isna()
        | d["dna_yield_norm"].isna()
        | d["protein_yield_norm"].isna()
        | d["activity_score"].isna()
        | ~np.isfinite(d["activity_score"].to_numpy())
        | ~np.isfinite(d["dna_yield_norm"].to_numpy())
        | ~np.isfinite(d["protein_yield_norm"].to_numpy())
    )
    d.loc[bad_mask, "qc_stage4"] = "invalid_fallback"

    ok = d[d["qc_stage4"] == "ok"].copy()

    rows: list[dict[str, Any]] = []
    for r in ok.itertuples(index=False):
        variant_id = int(r.variant_id)
        generation_id = int(r.generation_id)

        rows.append(
            dict(
                generation_id=generation_id,
                variant_id=variant_id,
                wt_control_id=None,
                metric_name="dna_yield_norm",
                metric_type="normalized",
                value=float(r.dna_yield_norm),
                unit="ratio",
                metric_definition_id=None,
            )
        )
        rows.append(
            dict(
                generation_id=generation_id,
                variant_id=variant_id,
                wt_control_id=None,
                metric_name="protein_yield_norm",
                metric_type="normalized",
                value=float(r.protein_yield_norm),
                unit="ratio",
                metric_definition_id=None,
            )
        )
        rows.append(
            dict(
                generation_id=generation_id,
                variant_id=variant_id,
                wt_control_id=None,
                metric_name="activity_score",
                metric_type="derived",
                value=float(r.activity_score),
                unit="ratio",
                metric_definition_id=None,
            )
        )

    return rows, d


def _normalize_plasmid_index(value: Any) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        as_num = float(text)
        if as_num.is_integer():
            return str(int(as_num))
    except (TypeError, ValueError):
        pass
    return text


def _build_placeholder_edges(
    df_nodes: pd.DataFrame,
    *,
    node_id_col: str,
    generation_col: str,
    index_col: str,
    max_distance: float,
) -> pd.DataFrame:
    """
    Create synthetic parent edges when parent_variant_id is missing.
    Strategy: nearest numeric index in previous generation within max_distance.
    """
    required = {node_id_col, generation_col, index_col}
    if not required.issubset(df_nodes.columns):
        return pd.DataFrame(columns=["parent_id", "child_id"])

    d = df_nodes[[node_id_col, generation_col, index_col]].copy()
    d[generation_col] = pd.to_numeric(d[generation_col], errors="coerce")
    d = d.dropna(subset=[node_id_col, generation_col])
    if d.empty:
        return pd.DataFrame(columns=["parent_id", "child_id"])

    d["_idx_str"] = d[index_col].map(_normalize_plasmid_index)
    d["_idx_num"] = pd.to_numeric(d["_idx_str"], errors="coerce")

    groups = {int(g): sub.copy() for g, sub in d.groupby(generation_col)}
    if not groups:
        return pd.DataFrame(columns=["parent_id", "child_id"])

    min_gen = min(groups.keys())
    edges: list[tuple[int, int]] = []

    for gen, sub in groups.items():
        if gen <= min_gen:
            continue
        prev = groups.get(gen - 1)
        if prev is None or prev.empty:
            continue

        prev_num = prev.dropna(subset=["_idx_num"])[["_idx_num", node_id_col]].to_numpy()

        for _, row in sub.iterrows():
            child_id = row[node_id_col]
            idx_str = row["_idx_str"]
            idx_num = row["_idx_num"]

            parent_id = None
            if pd.notna(idx_num) and len(prev_num) > 0:
                diffs = np.abs(prev_num[:, 0].astype(float) - float(idx_num))
                min_idx = int(diffs.argmin())
                if float(diffs[min_idx]) <= max_distance:
                    parent_id = int(prev_num[min_idx, 1])

            if parent_id is not None:
                edges.append((int(parent_id), int(child_id)))

    return pd.DataFrame(edges, columns=["parent_id", "child_id"])


def main() -> None:
    experiment_id = int(os.getenv("EXPERIMENT_ID", "0"))
    if experiment_id <= 0:
        raise SystemExit("Set EXPERIMENT_ID (e.g. export EXPERIMENT_ID=1)")

    ensure_sequence_processing_ready(experiment_id)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    qc_path = OUTPUT_DIR / f"exp_{experiment_id}_analysis.csv"
    top10_path = OUTPUT_DIR / f"exp_{experiment_id}_top10_variants.csv"
    plot_path = OUTPUT_DIR / f"exp_{experiment_id}_activity_distribution.png"
    lineage_path = OUTPUT_DIR / f"exp_{experiment_id}_lineage.png"
    # Default to mutation co-occurrence unless explicitly overridden.
    protein_mode = os.getenv("PROTEIN_NET_MODE", "cooccurrence").strip().lower()
    if protein_mode not in {"identity", "cooccurrence"}:
        protein_mode = "cooccurrence"

    # Scoring mode:
    # - auto: use WT-based when any WT baselines exist; fallback only if none exist
    # - wt: require WT baselines for all generations
    # - fallback: always use WT-free fallback scoring
    scoring_mode = os.getenv("SCORING_MODE", "auto").strip().lower()
    if scoring_mode not in {"auto", "wt", "fallback"}:
        scoring_mode = "auto"
    require_wt_baseline = _env_bool("STAGE4_REQUIRE_WT_BASELINE", scoring_mode == "wt")

    protein_suffix = "" if protein_mode == "identity" else f"_{protein_mode}"
    protein_net_path = OUTPUT_DIR / f"exp_{experiment_id}_protein_similarity{protein_suffix}.png"

    with get_conn() as conn:
        # 1) Raw variant metrics
        df_variants = fetch_variant_raw(conn, experiment_id)
        print(f"[Stage4] Variants fetched from DB: {len(df_variants)}")
        if df_variants.empty:
            print("[Stage4] No variants returned for this experiment_id. Exiting.")
            return

        # 2) Stage4 scoring selection
        baselines: dict[int, tuple[float, float]] = {}
        missing_generations: list[int] = []
        baseline_label = "WT control baseline = 1.0"

        if scoring_mode in {"auto", "wt"}:
            baselines, missing_generations = fetch_wt_baselines(conn, experiment_id)

        if scoring_mode == "wt" and missing_generations:
            raise SystemExit(
                "[Stage4] WT-based scoring is required but WT baselines are missing for "
                f"generation(s): {missing_generations} (experiment {experiment_id})."
            )
        if require_wt_baseline and scoring_mode != "fallback" and missing_generations:
            raise SystemExit(
                "[Stage4] STAGE4_REQUIRE_WT_BASELINE=true but WT baselines are missing for "
                f"generation(s): {missing_generations} (experiment {experiment_id})."
            )

        if baselines:
            print(f"[Stage4] WT baselines found for generations: {len(baselines)}")
            if missing_generations:
                print(
                    "[Stage4] Missing WT baselines for generation(s) "
                    f"{missing_generations}; those generations will be unscored and excluded."
                )
            rows_to_insert, df_with_qc = compute_stage4_metrics(df_variants, baselines)
            print("[Stage4] Activity score computed using: WT-normalised")
        else:
            if require_wt_baseline and scoring_mode != "fallback":
                raise SystemExit(
                    "[Stage4] STAGE4_REQUIRE_WT_BASELINE=true but no valid WT baselines were found "
                    f"for experiment {experiment_id}."
                )
            baseline_label = "Generation median baseline = 1.0"
            print("[Stage4] WT baselines unavailable; switching to fallback scoring: no valid WT baselines")
            rows_to_insert, df_with_qc = compute_activity_score_fallback(df_variants)
            print("[Stage4] Activity score computed using: median-normalised fallback")

        # ---- QC summary ----
        if "qc_stage4" in df_with_qc.columns:
            qc_counts = df_with_qc["qc_stage4"].value_counts(dropna=False)
            ok_n = int((df_with_qc["qc_stage4"] == "ok").sum())
            print(f"[Stage4] Total variants processed: {len(df_with_qc)}")
            print("[Stage4] QC summary:\n", qc_counts.to_string())
            print(f"[Stage4] OK variants: {ok_n}")
        print(f"[Stage4] rows_to_insert: {len(rows_to_insert)} (expected ~OK*3)")
        # --------------------

        # Hard validation for consistent scoring behavior across experiments.
        _validate_stage4_formula(df_with_qc)
        print("[Stage4] Validation passed: activity_score formula consistency")

        # 3) Upsert computed metrics into DB
        inserted_attempted = upsert_variant_metrics(conn, rows_to_insert)
        print(f"[DB] Upsert attempted rows: {inserted_attempted}")

        # Truth-check: do we have activity_score rows now?
        all_scores, exp_scores = db_count_activity_scores(conn, experiment_id)
        print(f"[DB] activity_score rows (all experiments): {all_scores}")
        print(f"[DB] activity_score rows (this experiment): {exp_scores}")

        # 4) Write QC debug CSV
        df_with_qc.to_csv(qc_path, index=False)
        print("[File] Wrote:", qc_path)

        # 5) Top-10 table + PNG
        df_top10 = fetch_top10(conn, experiment_id)
        _validate_top10_consistency(df_with_qc, df_top10)
        print("[Top10] Validation passed: top10 rows match highest activity scores")
        df_top10.to_csv(top10_path, index=False)
        print("[File] Wrote:", top10_path, f"(rows={len(df_top10)})")

        if df_top10.empty:
            print("[Top10] No top10 rows returned (activity_score may be missing or filtered).")
        else:
            plot_top10_table(df_top10, top10_path.with_suffix(".png"))
            print("[File] Wrote:", top10_path.with_suffix(".png"))

        # 6) Distribution plot
        df_dist = fetch_distribution(conn, experiment_id)
        if df_dist.empty:
            print(
                "[Plot] No distribution data returned.\n"
                "      Check activity_score presence and the DB counts above."
            )
            return

        plot_activity_distribution(df_dist, str(plot_path), baseline_label=baseline_label)
        print("[File] Wrote:", plot_path)

        # 7) Lineage plot
        df_nodes = fetch_lineage_nodes(conn, experiment_id)
        df_edges = fetch_lineage_edges(conn, experiment_id)

        df_nodes = df_nodes.copy()
        df_edges = df_edges.copy()

        df_nodes["variant_id"] = pd.to_numeric(df_nodes["variant_id"], errors="coerce").astype("Int64")
        df_edges["parent_id"] = pd.to_numeric(df_edges["parent_id"], errors="coerce").astype("Int64")
        df_edges["child_id"] = pd.to_numeric(df_edges["child_id"], errors="coerce").astype("Int64")
        df_edges = df_edges.dropna(subset=["parent_id", "child_id"])

        print("nodes:", len(df_nodes))
        print("edges:", len(df_edges))

        if df_edges.empty:
            df_edges = _build_placeholder_edges(
                df_nodes,
                node_id_col="variant_id",
                generation_col="generation_number",
                index_col="plasmid_variant_index",
                max_distance=3.0,
            )
            print("[Lineage] Using placeholder edges:", len(df_edges))

        node_ids = set(df_nodes["variant_id"])
        matching = (
            df_edges["parent_id"].isin(node_ids) &
            df_edges["child_id"].isin(node_ids)
        ).sum()

        print("edges matching nodes:", matching)

        if df_nodes.empty:
            print("[Lineage] No lineage nodes returned; skipping lineage plot.")
            return

        plot_layered_lineage(
            df_nodes,
            df_edges,
            lineage_path,
            node_id_col="variant_id",
            generation_col="generation_number",
            parent_col="parent_id",
            child_col="child_id",
            mutations_col="total_mutations",
        )
        print("[File] Wrote:", lineage_path)

        # 8) Protein similarity network
        df_protein = fetch_protein_similarity_nodes(conn, experiment_id)
        if df_protein.empty:
            print("[ProteinNet] No nodes returned; skipping protein similarity plot.")
            return

        if protein_mode == "identity" and df_protein["protein_sequence"].dropna().empty:
            print("[ProteinNet] No protein sequences available; skipping protein similarity plot.")
            return

        protein_mutations = None
        if protein_mode == "cooccurrence":
            protein_mutations = fetch_protein_mutations(conn, experiment_id)
            protein_cfg = ProteinNetConfig(
                mode="cooccurrence",
                cooccur_min_shared_mutations=1,
                top_n_by_activity=40,
                max_nodes_final=40,
                cooccur_focus_top10_neighbors=False,
                title="Protein Co-Occurrence Network (Top 40 Variants by Activity)",
            )
        else:
            protein_cfg = ProteinNetConfig(
                mode="identity",
                title="Protein Similarity Network",
            )

        plot_protein_similarity_network(
            df_protein,
            protein_net_path,
            id_col="variant_id",
            seq_col="protein_sequence",
            activity_col="activity_score",
            top_col="is_top10",
            mutations=protein_mutations,
            mode=protein_mode,
            config=protein_cfg,
        )
        print("[File] Wrote:", protein_net_path)


if __name__ == "__main__":
    main()
