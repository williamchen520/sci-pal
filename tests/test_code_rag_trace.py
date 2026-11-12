"""Bounded trace tests without a live database."""

from __future__ import annotations

import unittest
from unittest import mock

from code_rag.trace import trace


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if "code_edges" in sql:
            return _Result([("u1", "u2", "calls", "high"), ("u2", "u3", "calls", "medium")])
        return _Result([("u1", "a", "function", 1, 2, "a.py"), ("u2", "b", "function", 3, 4, "b.py")])


class TraceTests(unittest.TestCase):
    def test_trace_is_bounded(self) -> None:
        with mock.patch("code_rag.trace.psycopg.connect", return_value=_Conn()):
            result = trace(
                unit_id="u1",
                library_id="lib_1",
                direction="out",
                max_hops=2,
                max_nodes=2,
                dsn="postgresql://unused",
            )
        self.assertEqual(result["start"], "u1")
        self.assertTrue(result["truncated"])
        self.assertTrue(result["edges"])

    def test_invalid_direction(self) -> None:
        with self.assertRaises(ValueError):
            trace(unit_id="u1", library_id="lib_1", direction="sideways")


if __name__ == "__main__":
    unittest.main()
