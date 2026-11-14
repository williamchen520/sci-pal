"""HTML native read tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import html_native


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self):
        self.closed = False

    def execute(self, sql, params=()):
        if "FROM html_articles" in sql:
            return _Cursor([{"source_id": "src_1", "paper_id": "p1"}])
        if "FROM html_paragraphs WHERE source_id" in sql:
            return _Cursor([{"count": 3}])
        if "FROM html_sections" in sql:
            return _Cursor([{"native_section_id": "hsec_001", "title": "Results"}])
        return _Cursor([{"native_para_id": "hpara_001_001", "section_id": "hsec_001", "text": "T", "para_order": 1}])

    def close(self):
        self.closed = True


class HtmlNativeTests(unittest.TestCase):
    def test_summary(self) -> None:
        conn = _Conn()
        with mock.patch.object(html_native, "corpus_connection", return_value=conn):
            result = html_native.html_native("p1")
        self.assertEqual(result["source_id"], "src_1")
        self.assertEqual(result["section_count"], 1)
        self.assertEqual(result["paragraph_count"], 3)
        self.assertTrue(conn.closed)

    def test_missing(self) -> None:
        class _Empty(_Conn):
            def execute(self, sql, params=()):
                return _Cursor([])

        with mock.patch.object(html_native, "corpus_connection", return_value=_Empty()):
            self.assertIsNone(html_native.html_native("p1"))


if __name__ == "__main__":
    unittest.main()
