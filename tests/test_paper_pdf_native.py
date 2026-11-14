"""PDF native read tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import pdf_native


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
        if "FROM pdf_documents" in sql:
            return _Cursor([{"source_id": "src_1", "page_count": 2}])
        if "count(*) AS count" in sql:
            return _Cursor([{"count": 4}])
        return _Cursor([{"native_para_id": "p1", "para_id": "p1", "page": 1, "bbox": "0,0,1,1", "text": "T", "para_order": 1}])

    def close(self):
        self.closed = True


class PdfNativeTests(unittest.TestCase):
    def test_summary(self) -> None:
        conn = _Conn()
        with mock.patch.object(pdf_native, "corpus_connection", return_value=conn):
            result = pdf_native.pdf_native("p1", include_paragraphs=True)
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["paragraph_count"], 4)
        self.assertEqual(result["paragraphs"][0]["page"], 1)
        self.assertTrue(conn.closed)

    def test_missing(self) -> None:
        class _Empty(_Conn):
            def execute(self, sql, params=()):
                return _Cursor([])

        with mock.patch.object(pdf_native, "corpus_connection", return_value=_Empty()):
            self.assertIsNone(pdf_native.pdf_native("p1"))


if __name__ == "__main__":
    unittest.main()
