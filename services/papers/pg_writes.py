"""PostgreSQL-primary paper metadata writes (Phase 2, opt-in).

Only workspace assignment is migrated first. SQLite stays a mirror for FTS and
legacy readers. Fail closed when the PG backend is explicitly enabled.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class PaperWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_PAPER_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg_connection():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["SCIPAL_PG_DSN"], row_factory=dict_row)


def update_workspace(paper_id: str, workspace_id: str, *, db_path: str | Path) -> bool:
    """Update papers.workspace_id in PG, then mirror to SQLite.

    Returns False when the PG paper write backend is disabled, so callers can
    keep the legacy SQLite path.
    """
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            row = pg.execute(
                "UPDATE papers SET workspace_id = %s WHERE paper_id = %s RETURNING paper_id",
                (workspace_id, paper_id),
            ).fetchone()
            if not row:
                raise PaperWriteError("paper not found in PostgreSQL")
    except PaperWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG paper workspace update failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "UPDATE papers SET workspace_id = ? WHERE paper_id = ?",
            (workspace_id, paper_id),
        )
        conn.commit()
    finally:
        conn.close()
    return True
