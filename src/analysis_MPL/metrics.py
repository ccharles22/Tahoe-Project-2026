from __future__ import annotations
from typing import Any, Dict, List


def upsert_variant_metrics(conn, rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0

    sql = """
    INSERT INTO metrics (generation_id, variant_id, metric_name, metric_type, value, unit)
    SELECT
        v.generation_id,
        %(variant_id)s,
        %(metric_name)s,
        %(metric_type)s,
        %(value)s,
        %(unit)s
    FROM variants v
    WHERE v.variant_id = %(variant_id)s
    ON CONFLICT (variant_id, metric_name, metric_type)
    DO UPDATE SET
        generation_id = EXCLUDED.generation_id,
        value         = EXCLUDED.value,
        unit          = EXCLUDED.unit;
    """

    with conn.cursor() as cur:
        cur.executemany(sql, rows)

    return len(rows)