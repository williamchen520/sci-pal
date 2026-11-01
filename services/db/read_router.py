"""P5 read canary router.

Only the read-only paper list is enabled in this phase. SQLite remains the
default and the fallback; PostgreSQL is used for a configured percentage of
requests. Any PG error falls back to SQLite.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

PAPER_COLUMNS = (
    "paper_id",
    "title",
    "authors",
    "journal",
    "year",
    "doi",
    "total_paragraphs",
    "total_figures",
    "total_tables",
    "workspace_id",
)


@dataclass
class ReadResult:
    rows: List[dict]
    backend: str
    fallback: bool = False
    error: Optional[str] = None


@dataclass
class DetailResult:
    payload: Optional[dict]
    backend: str
    fallback: bool = False
    error: Optional[str] = None


class ReadRouter:
    def __init__(
        self,
        sqlite_path: str | Path,
        *,
        pg_dsn: str = "",
        canary_percent: int = 0,
        seed: str = "",
        connector=None,
    ):
        self.sqlite_path = Path(sqlite_path)
        self.pg_dsn = pg_dsn
        self.canary_percent = max(0, min(100, int(canary_percent)))
        self.seed = seed or os.environ.get("SCIPAL_READ_CANARY_SEED", "scipal")
        self._connector = connector

    def should_use_pg(self, key: str) -> bool:
        if self.canary_percent <= 0 or not self.pg_dsn:
            return False
        if self.canary_percent >= 100:
            return True
        digest = hashlib.sha256(f"{self.seed}:{key}".encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % 100 < self.canary_percent

    def _sqlite_rows(self, workspace_id: str) -> List[dict]:
        conn = sqlite3.connect(f"file:{self.sqlite_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                f"SELECT {', '.join(PAPER_COLUMNS)} FROM papers "
                "WHERE workspace_id = ? "
                "ORDER BY year DESC, title COLLATE BINARY, paper_id",
                (workspace_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _pg_rows(self, workspace_id: str) -> List[dict]:
        if self._connector is not None:
            pg = self._connector()
            close = False
        else:
            import psycopg
            from psycopg.rows import dict_row

            pg = psycopg.connect(self.pg_dsn, row_factory=dict_row)
            close = True
        try:
            rows = pg.execute(
                f"SELECT {', '.join(PAPER_COLUMNS)} FROM papers "
                "WHERE workspace_id = %s "
                'ORDER BY year DESC NULLS LAST, title COLLATE "C", paper_id',
                (workspace_id,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if close:
                pg.close()

    def _pg_connection(self):
        if self._connector is not None:
            return self._connector(), False
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.pg_dsn, row_factory=dict_row), True

    def _pg_paper_detail(self, paper_id: str, workspace_id: str) -> Optional[dict]:
        pg, close = self._pg_connection()
        try:
            paper = pg.execute(
                "SELECT * FROM papers WHERE paper_id = %s AND workspace_id = %s",
                (paper_id, workspace_id),
            ).fetchone()
            if not paper:
                return None
            cites = pg.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.target_paper_id
                WHERE c.source_paper_id = %s AND c.relation = 'cites'
                  AND p.workspace_id = %s
                ORDER BY c.confidence DESC
                """,
                (paper_id, workspace_id),
            ).fetchall()
            cited_by = pg.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.source_paper_id
                WHERE c.target_paper_id = %s AND c.relation = 'cites'
                  AND p.workspace_id = %s
                ORDER BY c.confidence DESC
                """,
                (paper_id, workspace_id),
            ).fetchall()
            similar = pg.execute(
                """
                SELECT p.paper_id, p.title, p.year, c.confidence
                FROM cross_paper_index c
                JOIN papers p ON p.paper_id = c.target_paper_id
                WHERE c.source_paper_id = %s AND c.relation = 'similar'
                  AND p.workspace_id = %s
                ORDER BY c.confidence DESC LIMIT 10
                """,
                (paper_id, workspace_id),
            ).fetchall()
            return {
                "paper": dict(paper),
                "cites": [dict(row) for row in cites],
                "cited_by": [dict(row) for row in cited_by],
                "similar": [dict(row) for row in similar],
            }
        finally:
            if close:
                pg.close()

    def paper_detail(
        self, paper_id: str, workspace_id: str, *, canary_key: str = ""
    ) -> DetailResult:
        if not self.should_use_pg(canary_key or paper_id):
            return DetailResult(None, "sqlite")
        try:
            return DetailResult(self._pg_paper_detail(paper_id, workspace_id), "postgres")
        except Exception as exc:  # noqa: BLE001
            return DetailResult(None, "sqlite", fallback=True, error=str(exc)[:300])

    def list_papers(self, workspace_id: str, *, canary_key: str = "") -> ReadResult:
        if self.should_use_pg(canary_key or workspace_id):
            try:
                return ReadResult(self._pg_rows(workspace_id), "postgres")
            except Exception as exc:  # noqa: BLE001 - fallback is the safety net
                return ReadResult(
                    self._sqlite_rows(workspace_id),
                    "sqlite",
                    fallback=True,
                    error=str(exc)[:300],
                )
        return ReadResult(self._sqlite_rows(workspace_id), "sqlite")
