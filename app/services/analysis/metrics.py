"""Helpers for writing derived variant metrics into PostgreSQL."""

from __future__ import annotations
from typing import Any, Dict, List


def upsert_variant_metrics(conn, rows: List[Dict[str, Any]]) -> int:
    """Insert or update the supplied metric rows for analysed variants.

    Uses an update-first strategy: each row is first attempted as an UPDATE
    keyed on ``(variant_id, metric_name, metric_type)``; if no existing row
    matches, a new row is INSERTed with the ``generation_id`` resolved from
    the ``variants`` table.

    Args:
        conn: An active psycopg2 database connection (caller manages commit).
        rows: Each dict must contain keys ``variant_id``, ``metric_name``,
            ``metric_type``, ``value``, and ``unit``.

    Returns:
        The number of metric rows processed (inserted or updated).
    """
    if not rows:
        return 0

    # Phase 1: attempt to update an existing metric row matching the composite key.
    update_sql = """
    UPDATE metrics AS m
    SET
        value = %(value)s,
        unit = %(unit)s
    WHERE m.variant_id = %(variant_id)s
      AND m.metric_name = %(metric_name)s
      AND m.metric_type = %(metric_type)s;
    """

    # Phase 2: if UPDATE touched zero rows, insert a new metric row.
    insert_sql = """
    INSERT INTO metrics (generation_id, variant_id, metric_name, metric_type, value, unit)
    SELECT
        v.generation_id,
        %(variant_id)s,
        %(metric_name)s,
        %(metric_type)s,
        %(value)s,
        %(unit)s
    FROM variants v
    WHERE v.variant_id = %(variant_id)s;
    """

    with conn.cursor() as cur:
        for row in rows:
            cur.execute(update_sql, row)
            if cur.rowcount == 0:
                cur.execute(insert_sql, row)

    return len(rows)
