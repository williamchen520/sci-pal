"""P5 read-router tests (PostgreSQL only)."""

from __future__ import annotations

import unittest
from pathlib import Path

from services.db.read_router import ReadRouter


class FakePG:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error

    def execute(self, sql, params=None):
        if self.error:
            raise self.error
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class DetailFakePG:
    def execute(self, sql, params=None):
        return self

    def fetchone(self):
        return {"paper_id": "p1", "title": "PG detail", "workspace_id": "ws"}

    def fetchall(self):
        return [{"paper_id": "p2", "title": "Neighbor", "year": 2024, "confidence": 0.9}]

    def close(self):
        pass


class ReadRouterTests(unittest.TestCase):
    def test_list_uses_postgres(self) -> None:
        router = ReadRouter(
            Path("unused.db"),
            pg_dsn="x",
            connector=lambda: FakePG([{"paper_id": "p1", "title": "PG"}]),
        )
        result = router.list_papers("ws", canary_key="k")
        self.assertEqual(result.backend, "postgres")
        self.assertEqual(result.rows[0]["title"], "PG")

    def test_pg_error_is_returned_not_fallback(self) -> None:
        router = ReadRouter(
            Path("unused.db"),
            pg_dsn="x",
            connector=lambda: FakePG(error=RuntimeError("down")),
        )
        result = router.list_papers("ws", canary_key="k")
        self.assertEqual(result.backend, "postgres")
        self.assertEqual(result.rows, [])
        self.assertIn("down", result.error)

    def test_detail_uses_postgres(self) -> None:
        router = ReadRouter(
            Path("unused.db"),
            pg_dsn="x",
            connector=lambda: DetailFakePG(),
        )
        result = router.paper_detail("p1", "ws", canary_key="k")
        self.assertEqual(result.backend, "postgres")
        self.assertEqual(result.payload["paper"]["paper_id"], "p1")
        self.assertEqual(len(result.payload["cites"]), 1)


if __name__ == "__main__":
    unittest.main()
