from src.analysis_MPL.database import get_conn

#also add to allow get_conn() to work without exporting it directly to .env
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            print("DB connection OK:", cur.fetchone())