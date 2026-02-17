from __future__ import annotations
from typing import Iterable, Dict, Any, List
from psycopg2.extras import execute_values

UPSERT_SQL = """
INSERT INTO metrics (generation_id, variant_id, metric_name, metric_type, value, unit)
VALUES %s
ON CONFLICT (variant_id, metric_name, metric_type)
DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit;
"""

def upsert_variant_metrics(conn, rows: List[Dict[str, Any]]) -> int:
    """
    rows: list of dicts: {generation_id, variant_id, metric_name, metric_type, value, unit}
    Returns number of rows attempted.
    """
    if not rows:
        return 0

    values = [
        (r["generation_id"], r["variant_id"], r["metric_name"], r["metric_type"], r["value"], r.get("unit"))
        for r in rows
    ]

    with conn.cursor() as cur:
        execute_values(cur, UPSERT_SQL, values, page_size=1000)
    conn.commit()
    return len(rows)