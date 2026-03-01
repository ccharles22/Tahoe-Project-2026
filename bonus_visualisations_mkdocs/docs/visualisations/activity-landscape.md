# Activity Landscape

A 3-D surface (or scatter) plot of PCA- or t-SNE-embedded mutation vectors,
coloured by activity score.  The surface mode produces a mountain-range
topography with scatter dots sitting on the surface using a warm colour scale
(purple → orange → yellow).

## Output

`outputs/activity_landscape_pca_surface_all_gens.html`

## Function

```python
plot_activity_landscape_plotly(
    generation_id: int | None = None,
    method: "pca" | "tsne" = "pca",
    mode: "scatter" | "surface" = "scatter",
    grid_size: int = 60,
    out_path: Path | str = "outputs/activity_landscape.html",
) -> Path
```

### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `generation_id` | `int \| None` | `None` | Filter to a single generation. `None` plots all generations. |
| `method` | `"pca"` \| `"tsne"` | `"pca"` | Dimensionality-reduction method for X/Y axes. |
| `mode` | `"scatter"` \| `"surface"` | `"scatter"` | `surface` adds an IDW-interpolated mesh underneath the points. |
| `grid_size` | `int` | `60` | Resolution of the surface grid (higher = smoother but slower). |
| `out_path` | `Path` | — | Output HTML file path. |

## Data source

Reads from the `mv_activity_landscape` materialized view, which must contain
columns: `generation_id`, `plasmid_variant_index`, `activity_score`, `x`, `y`,
`protein_mutations`, and `method`.

## How it works

1. Fetches PCA (or t-SNE) embeddings + activity scores from the MV.
2. In **surface** mode, applies inverse-distance weighting (IDW) to
   interpolate scores onto a regular grid.
3. Renders the surface mesh (`go.Surface`) with scatter points (`go.Scatter3d`)
   placed on top.

!!! note
    If using t-SNE, pass `--include-tsne` to the pipeline so the embeddings are
    precomputed before plotting.
