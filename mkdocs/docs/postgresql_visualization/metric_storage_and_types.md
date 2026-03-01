# Metric Storage & Types

This page focuses on how metrics are structured and persisted in the database.

## Where metrics live

The main metric rows are stored in:

- `metrics`

An optional reference dictionary also exists:

- `metric_definitions`

## Row ownership

Each metric row is attached to either:

- a variant (`variant_id`)
- or a WT control (`wt_control_id`)

This allows the system to store both experimental variant measurements and the
wild-type baseline measurements used for normalization.

## Generation linkage

`generation_id` is populated automatically from the owning variant or WT control
record, so the metric remains aligned with the correct generation even when the
write path only provides `variant_id` or `wt_control_id`.

## Uniqueness model

For variant-scoped metrics, the storage model expects one logical row for each:

- generation
- variant
- metric name
- metric type

WT control metrics use the same idea, but keyed by `wt_control_id`.

This design prevents duplicate metric rows from accumulating during normal
recalculation and keeps reporting queries predictable.

## Upsert behavior

The application writes metric rows through an upsert path, so recalculations
update existing values instead of duplicating them.

Code path:

- `src/analysis_MPL/metrics.py`
- `upsert_variant_metrics`

Behavior:

- insert the metric if it does not exist
- update `value` and `unit` if the metric already exists

## Why this matters

This storage model is what allows:

- recalculating activity scores safely
- regenerating reports without duplicating metric rows
- ranking variants using the latest values only
