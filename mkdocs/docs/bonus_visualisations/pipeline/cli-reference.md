# CLI Reference

The bonus pipeline is normally triggered from the application, but the logic is
still organised as a dedicated pipeline component.

## Key runtime expectations

- it runs after the main analysis step
- it targets the latest generation of the current experiment
- it writes HTML outputs for the bonus explorer in Section 6

## Output behavior

For stable workspace rendering, the platform uses predictable bonus output
targets so the UI can always look for the same view slots.

When a bonus plot cannot be produced, the platform writes a placeholder page for
that slot instead of removing the slot entirely.
