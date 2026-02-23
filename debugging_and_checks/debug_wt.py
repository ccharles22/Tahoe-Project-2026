from src.analysis_MPL.database import get_conn
import pandas as pd

with get_conn() as conn:
    df = pd.read_sql("""
        SELECT COUNT(*) AS n
        FROM metrics
        WHERE metric_type='raw'
          AND wt_control_id IS NOT NULL;
    """, conn)
    print(df.to_string(index=False))

    df2 = pd.read_sql("""
        SELECT metric_name, COUNT(*) AS n
        FROM metrics
        WHERE metric_type='raw'
          AND wt_control_id IS NOT NULL
        GROUP BY metric_name
        ORDER BY n DESC;
    """, conn)
    print(df2.to_string(index=False))

    df3 = pd.read_sql("""
        SELECT
          COUNT(*) AS n,
          COUNT(generation_id) AS with_generation_id
        FROM metrics
        WHERE metric_type='raw'
          AND wt_control_id IS NOT NULL;
    """, conn)
    print(df3.to_string(index=False))
