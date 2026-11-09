"""Paper existence/filename/workspace store (PostgreSQL)."""

from __future__ import annotations

from services.db.pg_pool import pg_connection


class PaperStore:
    def __init__(self, db_path=None) -> None:
        self.db_path = db_path

    def exists(self, paper_id: str) -> bool:
        pg = pg_connection()
        try:
            return bool(
                pg.execute(
                    "SELECT 1 FROM papers WHERE paper_id = %s", (paper_id,)
                ).fetchone()
            )
        finally:
            pg.close()

    def filename(self, paper_id: str):
        pg = pg_connection()
        try:
            return pg.execute(
                "SELECT filename FROM papers WHERE paper_id = %s", (paper_id,)
            ).fetchone()
        finally:
            pg.close()

    def in_workspace(self, paper_id: str, workspace_id: str) -> bool:
        pg = pg_connection()
        try:
            return bool(
                pg.execute(
                    "SELECT 1 FROM papers WHERE paper_id = %s AND workspace_id = %s",
                    (paper_id, workspace_id),
                ).fetchone()
            )
        finally:
            pg.close()
