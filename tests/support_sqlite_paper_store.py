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

    def assign_workspace(self, paper_id: str, workspace_id: str) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            try:
                conn.execute(
                    "UPDATE papers SET workspace_id = ? WHERE paper_id = ?",
                    (workspace_id, paper_id),
                )
                conn.commit()
            except sqlite3.OperationalError:
                pass
        finally:
            conn.close()

    def supplementary_counts(self) -> dict:
        conn = sqlite3.connect(str(self.db_path))
        try:
            try:
                rows = conn.execute(
                    "SELECT paper_id, COUNT(*) AS cnt FROM supplementary_files GROUP BY paper_id"
                ).fetchall()
                return {row[0]: row[1] for row in rows}
            except sqlite3.OperationalError:
                return {}
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
