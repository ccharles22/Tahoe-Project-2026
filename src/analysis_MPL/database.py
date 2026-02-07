import os
import psycopg2

def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set. Use .env or export it.")
    return psycopg2.connect(url)
