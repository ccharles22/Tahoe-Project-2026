import os
os.environ['EXPERIMENT_ID'] = '40'

from src.analysis_MPL.database import get_conn
from src.analysis_MPL.queries import fetch_lineage_nodes, fetch_lineage_edges

experiment_id = 40
conn = get_conn()

nodes = fetch_lineage_nodes(conn, experiment_id)
edges = fetch_lineage_edges(conn, experiment_id)
conn.close()

print(f"Nodes: {nodes.shape}")
print(f"Edges: {edges.shape if edges is not None else 'None'}")

if edges is not None and not edges.empty:
    print(f"\nEdges columns: {edges.columns.tolist()}")
    print(f"Edges sample:\n{edges.head(10)}")
    print(f"\nParent IDs sample: {edges['parent_id'].unique()[:5]}")
    print(f"Child IDs sample: {edges['child_id'].unique()[:5]}")
    print(f"\nNode IDs sample: {nodes['variant_id'].unique()[:5]}")
else:
    print("\n⚠️  NO EDGES DATA!")
    print(f"Edges is None: {edges is None}")
    if edges is not None:
        print(f"Edges empty: {edges.empty}")
        print(f"Edges shape: {edges.shape}")
