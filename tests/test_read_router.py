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


class DetailFakePG:
    def __init__(self):
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1
        return self

    def fetchone(self):
        return {"paper_id": "p1", "title": "PG detail", "workspace_id": "ws"}

    def fetchall(self):
        return [{"paper_id": "p2", "title": "Neighbor", "year": 2024, "confidence": 0.9}]

    def close(self):
        pass


class ReadRouterDetailTests(unittest.TestCase):
    def test_detail_uses_postgres(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT)")
            conn.commit()
            conn.close()
            router = ReadRouter(
                db, pg_dsn="x", canary_percent=100,
                connector=lambda: DetailFakePG(),
            )
            result = router.paper_detail("p1", "ws", canary_key="k")
            self.assertEqual(result.backend, "postgres")
            self.assertEqual(result.payload["paper"]["paper_id"], "p1")
            self.assertEqual(len(result.payload["cites"]), 1)


if __name__ == "__main__":
    unittest.main()
