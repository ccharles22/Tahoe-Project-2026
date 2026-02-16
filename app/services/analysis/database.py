import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set. Put it in .env or export it.")
    return psycopg2.connect(url)

