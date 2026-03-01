# Pipeline Usage

Bonus visualisations are generated as part of **Step 5: Run Analysis** in the
workspace.

## Execution model

The bonus pipeline runs after the main report outputs are refreshed. It uses the
latest generation of the current experiment and attempts to generate as many
bonus views as possible.

## Best-effort behavior

The pipeline is intentionally best-effort:

- if one bonus view fails, the others can still be written
- if a required dataset is missing, the corresponding view is replaced by a
  clear placeholder page

This keeps Section 6 usable even when a particular plot cannot be computed for
the current experiment state.

## Relationship to the main analysis

- **Step 4** computes sequence outputs and mutation data
- **Step 5** computes the main analysis outputs and then generates the bonus
  visualisations

Because of this, bonus outputs should be interpreted as analysis-stage outputs,
not sequence-stage outputs.
