# Metric Storage & Types

This page focuses on how metrics are structured, categorized, and persisted in
the database so that recalculation and reporting remain predictable.

## Where metrics live

The main metric rows are stored in:

- `metrics`

An optional supporting dictionary also exists:

- `metric_definitions`

The `metric_definitions` table provides descriptions, naming conventions, and
units, while the `metrics` table holds the actual experiment data.

## Metric classes used in practice

The platform writes three main classes of metric rows:

- `raw`: direct experimental measurements
- `normalized`: baseline-scaled ratios
- `derived`: computed values such as `activity_score`

Examples:

- `dna_yield_raw`
- `protein_yield_raw`
- `dna_yield_norm`
- `protein_yield_norm`
- `activity_score`

## Row ownership

Each metric row is attached to either:

- a variant (`variant_id`)
- or a WT control (`wt_control_id`)

This allows the same metric table to store both experimental variant values and
wild-type baseline measurements.

## Generation linkage

`generation_id` is populated automatically from the owning variant or WT control
record. This keeps the metric aligned with the correct generation even when the
write path only provides `variant_id` or `wt_control_id`.

## Uniqueness model

For variant-scoped metrics, one logical row is expected for each combination of:

- generation
- variant
- metric name
- metric type

WT control metrics follow the same idea, keyed by `wt_control_id` instead of
`variant_id`.

This keeps recalculation idempotent and prevents uncontrolled duplicate rows.

## Upsert behavior

Metric rows are written through an upsert path, so recalculations update the
latest value instead of inserting a second logical copy.

Code path:

- `src/analysis_MPL/metrics.py`
- `upsert_variant_metrics(...)`

Behavior:

- insert the metric if it does not exist
- update `value` and `unit` if the metric already exists

## Units and interpretability

For normalized and derived score rows, the expected unit is a ratio-like value.
This matters because downstream pages compare those values directly rather than
treating them as absolute assay measurements.

## Why this matters

This storage model is what allows the platform to:

- recompute activity scores safely
- regenerate reports without duplicating metric rows
- rank variants using the latest consistent values
- trace a derived score back to the raw measurements that produced it
