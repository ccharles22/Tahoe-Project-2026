# Mutation Fingerprinting

Per-variant lollipop chart showing every amino-acid change along the protein
sequence.  Each marker is coloured by the generation in which the mutation was
first introduced, making it easy to see how mutations accumulate through the
directed-evolution lineage.

## Output

`outputs/mutation_fingerprint_selector.html`

An interactive dropdown lets users switch between the top-performing variants
without leaving the page.

## Functions

### `plot_mutation_fingerprint_dropdown` (primary)

```python
plot_mutation_fingerprint_dropdown(
    variant_ids: list[int],
    out_path: Path | str = "outputs/mutation_fingerprint_selector.html",
    protein_length: int | None = None,
) -> Path | None
```

Builds a single figure with a dropdown menu (`updatemenus`) that toggles
visibility between variant trace groups.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `variant_ids` | `list[int]` | — | Variant IDs to include in the selector. |
| `out_path` | `Path` | — | Output HTML file. |
| `protein_length` | `int \| None` | `None` | Protein length; auto-detected when `None`. |

### `plot_mutation_fingerprint` (single variant)

```python
plot_mutation_fingerprint(
    variant_id: int,
    out_path: Path | str,
    protein_length: int | None = None,
) -> Path | None
```

Plots a single variant's fingerprint to a standalone HTML file.

## Data flow

1. **`fetch_lineage(conn, variant_id)`** — recursive CTE walks the
   `variants` table from leaf to root, returning the full ancestor chain
   with `generation_number` (not `generation_id`).
2. **`fetch_mutations_for_variants(conn, ids)`** — retrieves all
   non-synonymous protein mutations for the variants in the chain.
3. **`compute_introduction_generation(chain, muts)`** — determines the
   earliest generation in which each position×mutation pair first appeared.

## Visual encoding

- **X-axis** — amino-acid position along the protein.
- **Marker colour** — generation of introduction (12-colour palette with
  modulo wrapping for >12 generations).
- **Label** — `original>mutated` with a `(m)` missense annotation.
- **Lollipop stems** — vertical lines from the protein bar to the marker,
  stacked when multiple mutations hit the same position.
- **Hover** — position, mutation label, generation, and mutation type.
