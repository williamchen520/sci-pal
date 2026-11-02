"""Synchronous PostgreSQL catch-up for watch writes.

Watch still writes SQLite first. When SCIPAL_WATCH_WRITE_BACKEND=postgres, this
helper replays the pending outbox before the watch run returns, so profiles,
runs, items, and seen rows reach PG without waiting for the background worker.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

from services.db.dual_write import replay

LOGGER = logging.getLogger(__name__)


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_WATCH_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def sync_pending(db_path: str | Path, *, limit: int = 500) -> dict | None:
    if not enabled():
        return None
    try:
        import psycopg

        from services.db.dual_write import ensure_outbox

        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            ensure_outbox(conn)
            with psycopg.connect(os.environ["SCIPAL_PG_DSN"]) as pg:
                result = replay(conn, pg, limit=limit)
            return result
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - watch run must not fail on sync
        LOGGER.warning("watch PG sync skipped: %s", exc)
        return None
