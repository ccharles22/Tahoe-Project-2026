from src.analysis_MPL.database import get_conn
import pandas as pd

SQL = """
SELECT
    m.metric_name,
    m.metric_type,
    COUNT(*) AS n
FROM metrics m
JOIN variants v ON v.variant_id = m.variant_id
JOIN generations g ON g.generation_id = v.generation_id
WHERE g.experiment_id = 1
GROUP BY m.metric_name, m.metric_type
ORDER BY n DESC;
"""

with get_conn() as conn:
    df = pd.read_sql(SQL, conn)
    print(df.to_string(index=False))
