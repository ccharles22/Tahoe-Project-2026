# Mutation Frequency by Position

Two-panel chart that reveals positional mutation hotspots across the protein.

## Output

`outputs/mutation_frequency_by_position.html`

## Function

```python
plot_mutation_frequency(
    out_path: Path | str = "outputs/mutation_frequency_by_position.html",
    show_domains: bool = True,
) -> Path
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `out_path` | `Path` | — | Output HTML file. |
| `show_domains` | `bool` | `True` | Whether to overlay domain background bands on the bottom panel. |

## Panels

### Top — Total frequency

- Single blue bar per amino-acid position.
- The top 5 hotspot positions are annotated with their count.
- Clean white background (no domain bands).

### Bottom — Per-generation breakdown

- Stacked area chart (`stackgroup`) coloured by generation.
- Domain background bands are shown as semi-transparent vertical rectangles.
- Domain names appear on hover via invisible marker traces (avoids label
  overlap with chart data).

## Data source

Queries the `mutations` table directly (filtered to `mutation_type = 'protein'`
and non-synonymous), joined with `generations` for `generation_number`.

## Colour palette

Uses the same 10-colour palette as the mutation fingerprint plot for visual
consistency across charts.
