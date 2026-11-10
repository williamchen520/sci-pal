# sql_guard: allow-file
"""SQLite ingest write backend for tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SqliteIngestWriter:
    def __init__(self, db_path) -> None:
        self.db_path = Path(db_path)

    def connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def write(self, conn, parsed, service):
        return service._write_batch_sqlite(conn, parsed)
