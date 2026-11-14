"""Paper source provenance tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import sources


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    def execute(self, sql, params=()):
        return _Cursor(self.rows)

    def close(self):
        self.closed = True


class SourceTests(unittest.TestCase):
    def test_list_sources(self) -> None:
        conn = _Conn([{"source_id": "src_1", "source_kind": "jats"}])
        with mock.patch.object(sources, "corpus_connection", return_value=conn):
            rows = sources.list_sources("p1")
        self.assertEqual(rows[0]["source_kind"], "jats")
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
