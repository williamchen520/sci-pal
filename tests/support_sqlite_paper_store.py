"""Test-only SQLite PaperStore (production is PostgreSQL-only)."""

from __future__ import annotations

import sqlite3


class SqlitePaperStore:
    def __init__(self, db_path) -> None:
        self.db_path = db_path

    def exists(self, paper_id: str) -> bool:
        conn = sqlite3.connect(str(self.db_path))
        try:
            return bool(
                conn.execute(
                    "SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)
                ).fetchone()
            )
        finally:
            conn.close()

    def filename(self, paper_id: str):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT filename FROM papers WHERE paper_id = ?", (paper_id,)
            ).fetchone()
        finally:
            conn.close()

    def in_workspace(self, paper_id: str, workspace_id: str) -> bool:
        conn = sqlite3.connect(str(self.db_path))
        try:
            try:
                return bool(
                    conn.execute(
                        "SELECT 1 FROM papers WHERE paper_id = ? AND workspace_id = ?",
                        (paper_id, workspace_id),
                    ).fetchone()
                )
            except sqlite3.OperationalError:
                return bool(
                    conn.execute(
                        "SELECT 1 FROM papers WHERE paper_id = ?", (paper_id,)
                    ).fetchone()
                )
        finally:
            conn.close()
