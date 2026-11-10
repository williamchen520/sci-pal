# sql_guard: allow-file
"""SQLite ingest task store for tests."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    imported INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    batch_size INTEGER NOT NULL DEFAULT 5,
    current TEXT,
    error TEXT,
    pmc_ids TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SqliteTaskStore:
    def __init__(self, db_path) -> None:
        self.db_path = Path(db_path)

    def _conn(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(SCHEMA)
        return conn

    def create(self, task_id: str, *, total: int, batch_size: int, pmc_ids: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO ingest_tasks "
                "(task_id,status,total,batch_size,pmc_ids,created_at,updated_at) "
                "VALUES (?, 'queued', ?, ?, ?, ?, ?)",
                (task_id, total, batch_size, pmc_ids, _now(), _now()),
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM ingest_tasks WHERE task_id = ?", (task_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def set(self, task_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn = self._conn()
        try:
            conn.execute(
                f"UPDATE ingest_tasks SET {assignments} WHERE task_id = ?",
                (*fields.values(), task_id),
            )
            conn.commit()
        finally:
            conn.close()

    def cancel(self, task_id: str) -> bool:
        conn = self._conn()
        try:
            cur = conn.execute(
                "UPDATE ingest_tasks SET cancel_requested = 1, updated_at = ? WHERE task_id = ?",
                (_now(), task_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def cancelled(self, task_id: str) -> bool:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT cancel_requested FROM ingest_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            return bool(row and row["cancel_requested"])
        finally:
            conn.close()
