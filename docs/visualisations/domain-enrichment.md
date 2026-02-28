# Domain Enrichment Heatmap

Cross-generation heatmap showing how non-synonymous mutations are distributed
across protein domains.  Rows are domains (sorted by total mutation count),
columns are generations.

## Output

`outputs/domain_enrichment_heatmap.html`

## Function

```python
plot_domain_enrichment(
    generation_id: int | None = None,
    metric: "nonsyn_count" | "nonsyn_per_residue" = "nonsyn_count",
    out_path: Path | str = "outputs/domain_enrichment_heatmap.html",
) -> Path
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `generation_id` | `int \| None` | `None` | Single generation → bar chart. `None` → cross-generation heatmap. |
| `metric` | `str` | `"nonsyn_count"` | Which metric to plot. `nonsyn_per_residue` normalises by domain length. |
| `out_path` | `Path` | — | Output HTML file. |

## Data source

Reads from the `mv_domain_mutation_enrichment` materialized view, joined with
the `generations` table for `generation_number`.

## Visual details

- **Colour scale** — YlOrRd (sequential warm).
- **Cell annotations** — mutation count displayed in each cell; text colour
  adapts (white on dark cells, black on light).
- **Cell gaps** — 2 px gap between cells for readability.
- **Row ordering** — domains sorted by descending total mutation count.

!!! tip
    Pass `metric="nonsyn_per_residue"` to normalise by domain length, which
    highlights smaller domains with disproportionately high mutation rates.
