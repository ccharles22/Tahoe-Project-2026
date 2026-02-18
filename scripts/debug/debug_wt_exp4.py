from app.services.analysis.database import get_conn
import pandas as pd

exp_id = 4
with get_conn() as conn:
    df = pd.read_sql(
        """
        SELECT COUNT(*) AS n
        FROM metrics m
        JOIN generations g ON g.generation_id = m.generation_id
        WHERE g.experiment_id = %s
          AND m.metric_type='raw'
          AND m.wt_control_id IS NOT NULL;
    """,
        conn,
        params=(exp_id,),
    )
    print(df.to_string(index=False))

    df2 = pd.read_sql(
        """
        SELECT m.metric_name, COUNT(*) AS n
        FROM metrics m
        JOIN generations g ON g.generation_id = m.generation_id
        WHERE g.experiment_id = %s
          AND m.metric_type='raw'
          AND m.wt_control_id IS NOT NULL
        GROUP BY m.metric_name
        ORDER BY n DESC;
    """,
        conn,
        params=(exp_id,),
    )
    print(df2.to_string(index=False))
