import os
import pandas as pd
from psycopg2.extras import RealDictCursor
from src.analysis_MPL.database import get_conn

NODES_SQL = """
SELECT
  v.variant_id,
  v.parent_variant_id,
  g.generation_number,
  v.plasmid_variant_index
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
JOIN variant_lineage_closure c ON c.descendant_id = v.variant_id
WHERE c.ancestor_id = %s AND c.distance <= %s
ORDER BY g.generation_number;
"""

EDGES_SQL = """
SELECT v.parent_variant_id AS source, v.variant_id AS target
FROM variants v
JOIN variant_lineage_closure c ON c.descendant_id = v.variant_id
WHERE c.ancestor_id = %s AND c.distance <= %s
  AND v.parent_variant_id IS NOT NULL;
"""

def main():
    root_variant_id = int(os.getenv("ROOT_VARIANT_ID", "0"))
    depth = int(os.getenv("DEPTH", "3"))
    if root_variant_id <= 0:
        raise SystemExit("Set ROOT_VARIANT_ID (e.g. export ROOT_VARIANT_ID=581)")

    outdir = os.path.join("app", "static", "generated")
    os.makedirs(outdir, exist_ok=True)

    with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(NODES_SQL, (root_variant_id, depth))
        nodes = pd.DataFrame(cur.fetchall())
        cur.execute(EDGES_SQL, (root_variant_id, depth))
        edges = pd.DataFrame(cur.fetchall())

    nodes_path = os.path.join(outdir, f"lineage_{root_variant_id}_nodes.csv")
    edges_path = os.path.join(outdir, f"lineage_{root_variant_id}_edges.csv")
    nodes.to_csv(nodes_path, index=False)
    edges.to_csv(edges_path, index=False)

    print("Wrote:")
    print(" -", nodes_path)
    print(" -", edges_path)

if __name__ == "__main__":
    main()