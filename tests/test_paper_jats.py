"""JATS native read tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import jats


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, article, sections):
        self.article = article
        self.sections = sections
        self.closed = False

    def execute(self, sql, params=()):
        if "FROM jats_articles" in sql:
            return _Cursor([self.article] if self.article else [])
        return _Cursor(self.sections)

    def close(self):
        self.closed = True


class JatsTests(unittest.TestCase):
    def test_reads_sections(self) -> None:
        conn = _Conn(
            {"source_id": "src_1", "article_type": "review-article"},
            [{"native_section_id": "s1", "sec_type": "results"}],
        )
        with mock.patch.object(jats, "corpus_connection", return_value=conn):
            result = jats.jats_native("p1")
        self.assertEqual(result["article_type"], "review-article")
        self.assertEqual(result["sections"][0]["sec_type"], "results")
        self.assertTrue(conn.closed)

    def test_missing(self) -> None:
        conn = _Conn(None, [])
        with mock.patch.object(jats, "corpus_connection", return_value=conn):
            self.assertIsNone(jats.jats_native("p1"))


if __name__ == "__main__":
    unittest.main()
