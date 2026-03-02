"""Helpers for writing derived variant metrics into PostgreSQL."""

from __future__ import annotations
from typing import Any, Dict, List


def upsert_variant_metrics(conn, rows: List[Dict[str, Any]]) -> int:
    """Insert or update the supplied metric rows for analysed variants."""
    if not rows:
        return 0

    update_sql = """
    UPDATE metrics AS m
    SET
        value = %(value)s,
        unit = %(unit)s
    WHERE m.variant_id = %(variant_id)s
      AND m.metric_name = %(metric_name)s
      AND m.metric_type = %(metric_type)s;
    """

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
