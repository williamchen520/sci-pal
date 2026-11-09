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

    def assign_workspace(self, paper_id: str, workspace_id: str) -> None:
        pg = pg_connection()
        try:
            pg.execute(
                "UPDATE papers SET workspace_id = %s WHERE paper_id = %s",
                (workspace_id, paper_id),
            )
            pg.commit()
        finally:
            pg.close()

    def supplementary_counts(self) -> dict:
        pg = pg_connection()
        try:
            rows = pg.execute(
                "SELECT paper_id, COUNT(*) AS cnt FROM supplementary_files GROUP BY paper_id"
            ).fetchall()
            return {row["paper_id"]: row["cnt"] for row in rows}
        except Exception:
            return {}
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
