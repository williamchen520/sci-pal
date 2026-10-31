"""P5 read-canary router tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.db.read_router import ReadRouter


class FakePG:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.closed = False

    def execute(self, sql, params=None):
        if self.error:
            raise self.error
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class ReadRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            """
            CREATE TABLE papers (
              paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT,
              year INTEGER, doi TEXT, total_paragraphs INTEGER,
              total_figures INTEGER, total_tables INTEGER, workspace_id TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO papers VALUES ('p1','SQLite','a','j',2024,'d',1,0,0,'ws')"
        )
        conn.commit()
        conn.close()

    def test_canary_zero_uses_sqlite(self) -> None:
        router = ReadRouter(self.db, pg_dsn="x", canary_percent=0)
        result = router.list_papers("ws", canary_key="k")
        self.assertEqual(result.backend, "sqlite")
        self.assertEqual(result.rows[0]["title"], "SQLite")

    def test_canary_full_uses_postgres(self) -> None:
        fake = FakePG([{"paper_id": "p1", "title": "PG"}])
        router = ReadRouter(
            self.db, pg_dsn="x", canary_percent=100, connector=lambda: fake
        )
        result = router.list_papers("ws", canary_key="k")
        self.assertEqual(result.backend, "postgres")
        self.assertEqual(result.rows[0]["title"], "PG")

    def test_pg_error_falls_back(self) -> None:
        router = ReadRouter(
            self.db,
            pg_dsn="x",
            canary_percent=100,
            connector=lambda: FakePG(error=RuntimeError("down")),
        )
        result = router.list_papers("ws", canary_key="k")
        self.assertEqual(result.backend, "sqlite")
        self.assertTrue(result.fallback)
        self.assertIn("down", result.error)


if __name__ == "__main__":
    unittest.main()
