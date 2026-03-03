"""Database connection helpers for the analysis service layer."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


@contextmanager
def get_conn() -> Iterator[psycopg2.extensions.connection]:
    """
    Context-managed PostgreSQL connection.

    - Reads DATABASE_URL from environment or .env
    - Commits on success
    - Rolls back on exception
    - Always closes the connection

    Usage:
        with get_conn() as conn:
            ...
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set. Put it in .env or export it.")

    # Strip SQLAlchemy dialect suffixes so psycopg2 can parse the DSN.
    # e.g. "postgresql+psycopg://…" → "postgresql://…"
    if url.startswith("postgresql+"):
        url = "postgresql" + url[url.index("://"):]

    conn = psycopg2.connect(url, connect_timeout=5)

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_cursor(conn):
    """
    Returns a cursor that yields rows as dictionaries.
    """
    return conn.cursor(cursor_factory=RealDictCursor)
