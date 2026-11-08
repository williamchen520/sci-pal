"""Shared PostgreSQL connection pool.

One pool per DSN, sized by environment variables:
  SCIPAL_PG_POOL_MIN      default 1
  SCIPAL_PG_POOL_MAX      default 10
  SCIPAL_PG_POOL_TIMEOUT  default 5 seconds
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

_POOLS: Dict[str, Any] = {}
_LOCK = threading.Lock()


def pool_settings() -> dict:
    return {
        "min_size": max(0, int(os.environ.get("SCIPAL_PG_POOL_MIN", "1"))),
        "max_size": max(1, int(os.environ.get("SCIPAL_PG_POOL_MAX", "10"))),
        "timeout": max(0.1, float(os.environ.get("SCIPAL_PG_POOL_TIMEOUT", "5"))),
    }


def _dsn(dsn: Optional[str] = None) -> str:
    value = (dsn or os.environ.get("SCIPAL_PG_DSN", "")).strip()
    if not value:
        raise RuntimeError("SCIPAL_PG_DSN is not configured")
    return value


def _get_pool(dsn: str):
    """Lazy-import psycopg_pool so non-PG installs still import this module."""
    with _LOCK:
        if dsn in _POOLS:
            return _POOLS[dsn]
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        cfg = pool_settings()
        pool = ConnectionPool(
            conninfo=dsn,
            min_size=cfg["min_size"],
            max_size=cfg["max_size"],
            timeout=cfg["timeout"],
            kwargs={"row_factory": dict_row},
            name="scipal-pg",
            open=True,
        )
        _POOLS[dsn] = pool
        return pool


class PooledConnection:
    """Connection lease that returns to the pool on close/context exit."""

    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn
        self._closed = False

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._finish(exc_type is not None)
        return False

    def _finish(self, failed: bool) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if failed:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self._pool.putconn(self._conn)

    def close(self) -> None:
        self._finish(False)


def pg_connection(dsn: Optional[str] = None):
    """Return a pooled connection lease.

    Falls back to a direct psycopg connection when psycopg_pool is unavailable
    or the pool cannot be created, so existing deployments keep working.
    """
    dsn = _dsn(dsn)
    try:
        pool = _get_pool(dsn)
        return PooledConnection(pool, pool.getconn())
    except ImportError:
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(dsn, row_factory=dict_row)


def main_read_connection():
    """Read-only main-library connection (P4b1)."""
    dsn = os.environ.get("SCIPAL_PG_MAIN_READ_DSN", "").strip()
    if not dsn:
        logging.getLogger(__name__).warning(
            "SCIPAL_PG_MAIN_READ_DSN missing; falling back to owner DSN"
        )
        return pg_connection()
    return pg_connection(dsn)


def ingest_connection():
    """Ingest connection: main-library content writes, no tenant writes."""
    dsn = os.environ.get("SCIPAL_PG_INGEST_DSN", "").strip()
    if not dsn:
        logging.getLogger(__name__).warning(
            "SCIPAL_PG_INGEST_DSN missing; falling back to owner DSN"
        )
        return pg_connection()
    return pg_connection(dsn)


def admin_connection():
    """Admin connection for identity/migration writes."""
    dsn = os.environ.get("SCIPAL_PG_ADMIN_DSN", "").strip()
    if not dsn:
        logging.getLogger(__name__).warning(
            "SCIPAL_PG_ADMIN_DSN missing; falling back to owner DSN"
        )
        return pg_connection()
    return pg_connection(dsn)


def owner_connection():
    """Owner connection for papers/ingest/admin writes."""
    dsn = os.environ.get("SCIPAL_PG_OWNER_DSN", "").strip()
    if not dsn:
        logging.getLogger(__name__).warning(
            "SCIPAL_PG_OWNER_DSN missing; falling back to default DSN"
        )
        return pg_connection()
    return pg_connection(dsn)


def tenant_write_connection():
    """Tenant-writer connection (P4b1; used only by tenant-aware paths)."""
    dsn = os.environ.get("SCIPAL_PG_TENANT_WRITE_DSN", "").strip()
    if not dsn:
        logging.getLogger(__name__).warning(
            "SCIPAL_PG_TENANT_WRITE_DSN missing; falling back to owner DSN"
        )
        return pg_connection()
    return pg_connection(dsn)


def close_pools() -> None:
    """Close all pools (tests/shutdown)."""
    with _LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        try:
            pool.close()
        except Exception:  # noqa: BLE001
            pass


def pool_status() -> dict:
    """Return lightweight pool metrics for health/diagnostics."""
    out = {}
    for dsn, pool in list(_POOLS.items()):
        try:
            out["scipal"] = {
                "min_size": pool.min_size,
                "max_size": pool.max_size,
                "size": pool.get_stats().get("pool_size"),
                "available": pool.get_stats().get("pool_available"),
                "requests_waiting": pool.get_stats().get("requests_waiting"),
            }
        except Exception:  # noqa: BLE001
            out["scipal"] = {"error": "status unavailable"}
    return out
