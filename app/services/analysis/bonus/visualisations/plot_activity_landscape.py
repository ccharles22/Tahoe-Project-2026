"""Plotly-based bonus landscape visualisation for activity embeddings."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE

from app.services.analysis.bonus.database.postgres import get_connection
from app.services.analysis.bonus.features.mutation_vector import build_mutation_matrix


def _grid_interpolate_idw(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    grid_size: int = 60,
    power: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Inverse-distance weighting (IDW) onto a regular grid.

    Args:
        x: Scatter-point X coordinates.
        y: Scatter-point Y coordinates.
        z: Scatter-point Z values (e.g. activity scores).
        grid_size: Number of grid cells per axis.
        power: Distance exponent controlling influence decay.

    Returns:
        Tuple of ``(Xg, Yg, Zg)`` meshgrid arrays for surface plotting.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)

    xi = np.linspace(x.min(), x.max(), grid_size)
    yi = np.linspace(y.min(), y.max(), grid_size)
    Xg, Yg = np.meshgrid(xi, yi)

    Zg = np.empty_like(Xg, dtype=float)
    eps = 1e-12

    for i in range(grid_size):
        for j in range(grid_size):
            dx = x - Xg[i, j]
            dy = y - Yg[i, j]
            d2 = dx * dx + dy * dy + eps
            w = 1.0 / (d2 ** (power / 2.0))
            Zg[i, j] = np.sum(w * z) / np.sum(w)

    return Xg, Yg, Zg


def _load_experiment_landscape_frame(
    generation_id: int,
    method: Literal["pca", "tsne"],
) -> tuple[int, pd.DataFrame]:
    """Return experiment-wide activity rows with a fresh 2D embedding."""
    experiment_id, variants, muts = _load_experiment_landscape_inputs(generation_id)
    return experiment_id, _build_landscape_frame(variants, muts, method)


def _load_experiment_landscape_inputs(
    generation_id: int,
) -> tuple[int, pd.DataFrame, pd.DataFrame]:
    """Load experiment-wide variants and mutations for one generation context."""
    with get_connection() as conn:
        meta = pd.read_sql_query(
            """
            SELECT experiment_id
            FROM generations
            WHERE generation_id = %s
            """,
            conn,
            params=(generation_id,),
        )
        if meta.empty:
            raise RuntimeError(f"generation_id={generation_id} was not found.")

        experiment_id = int(meta.iloc[0]["experiment_id"])

        variants = pd.read_sql_query(
            """
            SELECT
              v.variant_id,
              v.plasmid_variant_index,
              g.generation_number,
              act.value AS activity_score,
              CASE
                WHEN NULLIF(v.extra_metadata #>> '{sequence_analysis,mutation_counts,total}', '') IS NOT NULL
                  THEN CAST(v.extra_metadata #>> '{sequence_analysis,mutation_counts,total}' AS integer)
                WHEN mut_metric.value IS NOT NULL
                  THEN CAST(mut_metric.value AS integer)
                ELSE NULL
              END AS mutation_total
            FROM variants v
            JOIN generations g
              ON g.generation_id = v.generation_id
            LEFT JOIN LATERAL (
                SELECT value
                FROM metrics m
                WHERE m.variant_id = v.variant_id
                  AND m.metric_type = 'derived'
                  AND m.metric_name = 'activity_score'
                ORDER BY m.metric_id DESC
                LIMIT 1
            ) act ON TRUE
            LEFT JOIN LATERAL (
                SELECT value
                FROM metrics m
                WHERE m.variant_id = v.variant_id
                  AND m.metric_type = 'derived'
                  AND m.metric_name = 'mutation_total_count'
                ORDER BY m.metric_id DESC
                LIMIT 1
            ) mut_metric ON TRUE
            WHERE g.experiment_id = %s
            """,
            conn,
            params=(experiment_id,),
        )

        muts = pd.read_sql_query(
            """
            SELECT
              m.variant_id,
              m.mutation_type,
              m.position,
              m.mutated
            FROM mutations m
            JOIN variants v
              ON v.variant_id = m.variant_id
            JOIN generations g
              ON g.generation_id = v.generation_id
            WHERE g.experiment_id = %s
            """,
            conn,
            params=(experiment_id,),
        )
    return experiment_id, variants, muts


def _build_landscape_frame(
    variants: pd.DataFrame,
    muts: pd.DataFrame,
    method: Literal["pca", "tsne"],
) -> pd.DataFrame:
    """Build an experiment-wide 2D embedding frame from mutations + activity scores."""
    all_vids = variants["variant_id"].astype(int).tolist()
    X = build_mutation_matrix(muts)

    if X.empty:
        coords = pd.DataFrame({"variant_id": all_vids, "x": 0.0, "y": 0.0})
    else:
        X = X.reindex(all_vids, fill_value=0)
        if method == "pca":
            model = PCA(n_components=2, random_state=42)
            xy = model.fit_transform(X.values)
        else:
            n = X.shape[0]
            if n < 3:
                xy = np.zeros((n, 2), dtype=float)
            else:
                perplexity = min(30, max(2, n - 1))
                model = TSNE(
                    n_components=2,
                    perplexity=perplexity,
                    init="pca",
                    learning_rate="auto",
                    random_state=42,
                )
                xy = model.fit_transform(X.values)

        coords = pd.DataFrame({"variant_id": all_vids, "x": xy[:, 0], "y": xy[:, 1]})

    df = variants.merge(coords, on="variant_id", how="left")
    df = df.dropna(subset=["activity_score", "x", "y"])
    if df.empty:
        raise RuntimeError(
            "No usable experiment-wide rows after filtering for activity scores and embeddings."
        )

    df["mutation_total_label"] = df["mutation_total"].apply(
        lambda value: "N/A" if pd.isna(value) else str(int(value))
    )
    return df


def _add_landscape_traces(
    fig: go.Figure,
    frame: pd.DataFrame,
    method: Literal["pca", "tsne"],
    mode: Literal["scatter", "surface"],
    grid_size: int,
    *,
    visible: bool,
    label: str,
) -> None:
    """Append one surface/scatter view for a dataset scope."""
    x = frame["x"].to_numpy()
    y = frame["y"].to_numpy()
    z = frame["activity_score"].to_numpy()

    if mode == "surface":
        Xg, Yg, Zg = _grid_interpolate_idw(x, y, z, grid_size=grid_size, power=2.0)
        fig.add_trace(
            go.Surface(
                x=Xg,
                y=Yg,
                z=Zg,
                opacity=0.75,
                showscale=True,
                visible=visible,
                hovertemplate=(
                    f"{method.upper()}1: %{{x:.3f}}<br>"
                    f"{method.upper()}2: %{{y:.3f}}<br>"
                    "Activity: %{z:.3f}<extra></extra>"
                ),
                showlegend=False,
                name=f"{label} surface",
            )
        )

    fig.add_trace(
        go.Scatter3d(
            x=x,
            y=y,
            z=z,
            mode="markers",
            visible=visible,
            text=frame["plasmid_variant_index"],
            customdata=frame[["generation_number", "mutation_total_label"]].to_numpy(),
            marker=dict(size=5),
            showlegend=False,
            hovertemplate=(
                "Variant: %{text}<br>"
                "Generation: %{customdata[0]}<br>"
                f"{method.upper()}1: %{{x:.3f}}<br>"
                f"{method.upper()}2: %{{y:.3f}}<br>"
                "Activity: %{z:.3f}<br>"
                "Total muts: %{customdata[1]}<extra></extra>"
            ),
            name=f"{label} variants",
        )
    )


def plot_activity_landscape_plotly(
    generation_id: int,
    method: Literal["pca", "tsne"] = "pca",
    mode: Literal["scatter", "surface"] = "scatter",
    grid_size: int = 60,
    out_path: Path | str = "outputs/activity_landscape.html",
) -> Path:
    """Generate a 3D Plotly activity landscape with dropdown view selector.

    X/Y axes are derived from PCA or t-SNE of the mutation-vector
    space; Z axis represents the activity score.  'scatter' shows raw
    data points; 'surface' adds an IDW-interpolated topography beneath.

    Args:
        generation_id: Any generation in the target experiment (used to
            identify the experiment and load all its generations).
        method: Initial dimensionality reduction method shown.
        mode: Initial rendering style.
        grid_size: Surface interpolation grid resolution.
        out_path: Destination for the self-contained HTML file.

    Returns:
        Path to the written HTML file.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    experiment_id, variants, muts = _load_experiment_landscape_inputs(generation_id)
    # Build both PCA and t-SNE embeddings so the dropdown can switch
    pca_df = _build_landscape_frame(variants, muts, "pca")
    tsne_df = _build_landscape_frame(variants, muts, "tsne")

    latest_generation = int(max(pca_df["generation_number"].max(), tsne_df["generation_number"].max()))
    pca_latest = pca_df[pca_df["generation_number"] == latest_generation].copy()
    tsne_latest = tsne_df[tsne_df["generation_number"] == latest_generation].copy()

    # Four view configurations: PCA/t-SNE × whole-experiment/latest-generation
    views: list[tuple[str, Literal["pca", "tsne"], pd.DataFrame]] = [
        ("Whole experiment", "pca", pca_df),
        (f"Latest generation ({latest_generation})", "pca", pca_latest),
        ("Whole experiment", "tsne", tsne_df),
        (f"Latest generation ({latest_generation})", "tsne", tsne_latest),
    ]
    # Surface mode adds an extra trace (the surface mesh) per group
    trace_group_size = 2 if mode == "surface" else 1
    initial_group = 0 if method == "pca" else 2

    fig = go.Figure()

    for idx, (scope_label, current_method, frame) in enumerate(views):
        _add_landscape_traces(
            fig,
            frame,
            current_method,
            mode,
            grid_size,
            visible=(idx == initial_group),
            label=f"{current_method.upper()} {scope_label}",
        )

    title_mode = "Surface + points" if mode == "surface" else "Points"
    initial_method = "PCA" if method == "pca" else "t-SNE"
    fig.update_layout(
        title=(
            f"3D Activity Landscape (Experiment {experiment_id}, All generations, "
            f"{initial_method}, {title_mode})"
        ),
        scene=dict(
            xaxis_title=f"{initial_method} dim 1",
            yaxis_title=f"{initial_method} dim 2",
            zaxis_title="Activity Score",
            domain=dict(x=[0.0, 1.0], y=[0.0, 1.0]),
            aspectmode="manual",
            aspectratio=dict(x=1.3, y=1.08, z=0.92),
            camera=dict(eye=dict(x=1.22, y=1.02, z=0.78)),
        ),
        updatemenus=[
            dict(
                type="buttons",
                direction="down",
                x=0.02,
                xanchor="left",
                y=1.0,
                yanchor="top",
                showactive=True,
                bgcolor="rgba(255,255,255,0.88)",
                bordercolor="rgba(148,163,184,0.7)",
                pad=dict(r=4, t=4),
                buttons=[
                    dict(
                        label=f"{'PCA' if current_method == 'pca' else 't-SNE'} - {scope_label}",
                        method="update",
                        args=[
                            {
                                "visible": [
                                    group_idx == idx
                                    for group_idx in range(len(views))
                                    for _ in range(trace_group_size)
                                ]
                            },
                            {
                                "title": (
                                    f"3D Activity Landscape (Experiment {experiment_id}, {scope_label}, "
                                    f"{'PCA' if current_method == 'pca' else 't-SNE'}, {title_mode})"
                                ),
                                "scene.xaxis.title": f"{'PCA' if current_method == 'pca' else 't-SNE'} dim 1",
                                "scene.yaxis.title": f"{'PCA' if current_method == 'pca' else 't-SNE'} dim 2",
                            },
                        ],
                    )
                    for idx, (scope_label, current_method, _) in enumerate(views)
                ],
            )
        ],
        autosize=True,
        height=760,
        margin=dict(l=18, r=18, t=96, b=16),
    )

    fig.write_html(str(out_path))
    return out_path


def main():
    """CLI entrypoint for exporting an interactive activity landscape."""
    ap = argparse.ArgumentParser(
        description="3D Activity Landscape: X/Y = PCA or t-SNE (diversity), Z = activity_score"
    )
    ap.add_argument("--generation-id", type=int, required=True)
    ap.add_argument("--method", choices=["pca", "tsne"], default="pca")
    ap.add_argument(
        "--mode",
        choices=["scatter", "surface"],
        default="scatter",
        help="scatter = points only; surface = interpolated topography + points overlay",
    )
    ap.add_argument("--grid-size", type=int, default=60, help="surface only: grid resolution")
    ap.add_argument("--out", default="outputs/activity_landscape.html")

    args = ap.parse_args()

    out = plot_activity_landscape_plotly(
        generation_id=args.generation_id,
        method=args.method,
        mode=args.mode,
        grid_size=args.grid_size,
        out_path=args.out,
    )
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
