"""Best-effort PostgreSQL sync for watch paper placeholder deletes.

Watch still writes through SQLite + outbox. This helper removes the placeholder
from PG immediately when present, then mirrors the SQLite delete; a missing PG
row is not an error.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class WatchWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_WATCH_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg_connection():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["SCIPAL_PG_DSN"], row_factory=dict_row)


def delete_paper_best_effort(paper_id: str, *, db_path: str | Path) -> bool:
    """Delete a watch placeholder in PG, then SQLite; return False if disabled.

    The SQLite delete still runs when PG is unavailable so the existing outbox
    can carry the delete later.
    """
    if not enabled():
        return False
    pg_deleted = False
    try:
        with _pg_connection() as pg:
            row = pg.execute(
                "DELETE FROM papers WHERE paper_id = %s RETURNING paper_id", (paper_id,)
            ).fetchone()
            pg_deleted = bool(row)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("PG watch paper delete skipped for %s: %s", paper_id, exc)

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
        conn.commit()
    finally:
        conn.close()
    return pg_deleted
