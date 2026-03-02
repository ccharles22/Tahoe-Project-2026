"""
PostgreSQL connection utilities.

This module provides a clean, reproducible way to connect to the project
PostgreSQL database using environment variables.

Supported configuration methods:

1) Preferred:
   DATABASE_URL=postgresql://user:password@host:port/database

2) Fallback:
   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE

Environment variables are loaded automatically from a .env file
(if present) using python-dotenv.

"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple

import psycopg2
from psycopg2.extensions import connection as PGConnection
from psycopg2.extras import execute_values
from dotenv import load_dotenv


load_dotenv()


def _build_dsn() -> str:
    """
    Priority: DATABASE_URL, then individual PG* variables.
    Raises RuntimeError if required values are missing.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    host = os.getenv("PGHOST")
    port = os.getenv("PGPORT", "5432")
    user = os.getenv("PGUSER")
    password = os.getenv("PGPASSWORD")
    dbname = os.getenv("PGDATABASE")

    missing = [
        k for k, v in {
            "PGHOST": host,
            "PGUSER": user,
            "PGPASSWORD": password,
            "PGDATABASE": dbname,
        }.items()
        if not v
    ]
    if missing:
        raise RuntimeError(f"Database configuration incomplete. Missing: {missing}")

    return f"dbname={dbname} user={user} password={password} host={host} port={port}"


def get_connection() -> PGConnection:
    """Opens a new connection with autocommit disabled."""
    dsn = _build_dsn()
    try:
        conn = psycopg2.connect(dsn)
        conn.autocommit = False
        return conn
    except Exception as e:
        raise RuntimeError(f"Failed to connect to PostgreSQL database: {e}") from e


@contextmanager
def db_conn() -> Generator[PGConnection, None, None]:
    """Yields a connection that auto-commits on success, rolls back on error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_cursor(commit: bool = False) -> Generator:
    """Yields a cursor; commits only when commit=True."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------------------------
# Metrics helpers (used by embedding precompute + pipeline)
# -------------------------------------------------------------------

def fetch_metric_definition_ids(conn: PGConnection, names: Sequence[str]) -> Dict[Tuple[str, str], int]:
    """Returns {(name, metric_type): metric_definition_id} for the given names."""
    if not names:
        return {}

    placeholders = ",".join(["%s"] * len(names))
    q = f"""
      SELECT metric_definition_id, name, metric_type
      FROM metric_definitions
      WHERE name IN ({placeholders})
    """
    with conn.cursor() as cur:
        cur.execute(q, tuple(names))
        rows = cur.fetchall()

    out: Dict[Tuple[str, str], int] = {}
    for mid, name, mtype in rows:
        out[(str(name), str(mtype))] = int(mid)
    return out


def delete_metrics_by_name(
    conn: PGConnection,
    generation_id: int,
    metric_names: List[str],
    metric_type: str = "derived",
) -> None:
    """Idempotent delete; only affects variant metrics, not wt_control rows."""
    if not metric_names:
        return

    q = """
      DELETE FROM metrics
      WHERE generation_id = %s
        AND metric_type = %s
        AND metric_name = ANY(%s)
        AND variant_id IS NOT NULL
    """
    with conn.cursor() as cur:
        cur.execute(q, (generation_id, metric_type, metric_names))


def bulk_insert_metrics(conn: PGConnection, rows: List[Dict[str, Any]]) -> None:
    """
    Each row must have exactly one of variant_id or wt_control_id set
    (schema constraint).
    """
    if not rows:
        return

    cols = [
        "generation_id",
        "variant_id",
        "wt_control_id",
        "metric_name",
        "metric_type",
        "value",
        "unit",
        "metric_definition_id",
    ]
    values = [tuple(r.get(c) for c in cols) for r in rows]

    q = f"INSERT INTO metrics ({','.join(cols)}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, q, values, page_size=1000)


def refresh_materialized_view(conn: PGConnection, view_name: str) -> None:
    """Refresh a single materialized view in the current transaction."""
    with conn.cursor() as cur:
        cur.execute(f"REFRESH MATERIALIZED VIEW {view_name};")


def refresh_views(conn: PGConnection, view_names: Sequence[str]) -> None:
    """Refresh each named materialized view in order."""
    for v in view_names:
        refresh_materialized_view(conn, v)
