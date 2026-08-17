"""PostgreSQL connection pool for the IA service.

Uses psycopg2 with a ThreadedConnectionPool for thread-safe access.
The pool is initialised at application startup and closed on shutdown.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool(database_url: str, min_connections: int = 2, max_connections: int = 10) -> None:
    """Create the connection pool. Call once at startup."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        logger.info("Connection pool already initialised, skipping.")
        return
    logger.info("Initialising PostgreSQL connection pool...")
    _pool = psycopg2.pool.ThreadedConnectionPool(
        min_connections,
        max_connections,
        database_url,
    )
    logger.info("Connection pool ready (min=%d, max=%d).", min_connections, max_connections)


def close_pool() -> None:
    """Close all connections in the pool. Call on shutdown."""
    global _pool  # noqa: PLW0603
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Connection pool closed.")


def is_initialized() -> bool:
    """Return whether the connection pool is available."""
    return _pool is not None


@contextmanager
def get_connection() -> Generator[Any, None, None]:
    """Borrow a connection from the pool (context manager).

    Usage::

        with get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT 1")
    """
    if _pool is None:
        raise RuntimeError("Connection pool not initialised. Call init_pool() first.")
    conn = _pool.getconn()
    if getattr(conn, "closed", 0) != 0:
        try:
            _pool.putconn(conn, close=True)
        except Exception:
            pass
        conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def execute_query(
    query: str,
    params: tuple | None = None,
    *,
    local_settings: dict[str, str] | None = None,
) -> list[dict]:
    """Execute a query and return results as a list of dicts.

    ``set_config(..., true)`` makes tuning transaction-local, so pooled
    connections cannot leak pgvector settings into subsequent requests.
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for setting, value in (local_settings or {}).items():
                cur.execute("SELECT set_config(%s, %s, true)", (setting, value))
            cur.execute(query, params)
            if cur.description is not None:
                return [dict(row) for row in cur.fetchall()]
            return []


def execute_many(query: str, params_list: list[tuple]) -> int:
    """Execute a parameterised query for many rows. Returns row count."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(query, params_list)
            return cur.rowcount


def execute_batch_insert(query: str, params_list: list[tuple], page_size: int = 100) -> None:
    """Efficient batch insert using psycopg2.extras.execute_batch."""
    from psycopg2.extras import execute_batch

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_batch(cur, query, params_list, page_size=page_size)
