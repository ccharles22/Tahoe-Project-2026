# CLI Reference

Full argument reference for the bonus visualisation pipeline.

```
python -m analysis.pipelines.run_bonus_pipeline [OPTIONS]
```

## Required

| Argument | Type | Description |
|---|---|---|
| `--generation-id` | `int` | Generation ID to process. Used for embedding precomputation and as a filter when `--fingerprint-variant-id` is set. |

## Output

| Argument | Type | Default | Description |
|---|---|---|---|
| `--sql-dir` | `str` | `sql` | Directory containing `views/*.sql` files. |
| `--outputs-dir` | `str` | `outputs` | Directory for generated HTML files. |

## Embedding options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--include-tsne` | flag | off | Also compute t-SNE embeddings (required if `--landscape-method tsne`). |
| `--perplexity` | `int` | `30` | t-SNE perplexity parameter. |
| `--seed` | `int` | `42` | Random seed for reproducibility. |

## Landscape options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--landscape-method` | `pca` \| `tsne` | `pca` | Dimensionality-reduction method for landscape axes. |
| `--landscape-mode` | `scatter` \| `surface` | `surface` | Render mode. `surface` adds an IDW-interpolated mesh. |
| `--grid-size` | `int` | `60` | Surface grid resolution. |

## Fingerprint options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--fingerprint-variant-id` | `int` | auto | Plot a specific variant. When omitted, auto-selects top 10 by activity and lineage depth. |

## Database options

| Argument | Type | Default | Description |
|---|---|---|---|
| `--skip-create-views` | flag | off | Skip `CREATE MATERIALIZED VIEW` statements (use when views already exist). |
| `--skip-refresh-views` | flag | off | Skip `REFRESH MATERIALIZED VIEW` (use when your role lacks refresh privileges). |
