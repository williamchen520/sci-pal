"""Paper reader service tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import reader


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.closed = False

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return _Cursor(self.rows)

    def close(self):
        self.closed = True


class PaperReaderTests(unittest.TestCase):
    def test_outline_normalizes_sections(self) -> None:
        conn = _Conn(
            [
                {
                    "section_path": "Results",
                    "section_level1": "Results",
                    "section_level2": None,
                    "paragraph_count": 3,
                    "first_para_id": "p1",
                }
            ]
        )
        with mock.patch.object(reader, "corpus_connection", return_value=conn):
            rows = reader.paper_outline("paper_1")
        self.assertEqual(rows[0]["section_path"], "Results")
        self.assertEqual(rows[0]["paragraph_count"], 3)
        self.assertEqual(rows[0]["first_para_id"], "p1")
        self.assertTrue(conn.closed)

    def test_body_heading_normalized(self) -> None:
        conn = _Conn(
            [
                {
                    "section_path": None,
                    "section_level1": "body",
                    "section_level2": "Establish a single-cell atlas",
                    "paragraph_count": 4,
                    "first_para_id": "p2",
                }
            ]
        )
        with mock.patch.object(reader, "corpus_connection", return_value=conn):
            rows = reader.paper_outline("paper_1")
        self.assertEqual(rows[0]["section_path"], "Establish a single-cell atlas")

    def test_paragraphs_section_filter(self) -> None:
        conn = _Conn([])
        with mock.patch.object(reader, "corpus_connection", return_value=conn):
            reader.paper_paragraphs("paper_1", section="Methods", offset=10, limit=5)
        sql, params = conn.calls[0]
        self.assertIn("p.section_level1 ILIKE", sql)
        self.assertIn("p.section_level1 NOT IN ('figure_caption','table_caption')", sql)
        self.assertIn("COALESCE(p.section_level2,'') !~*", sql)
        self.assertIn("p.text ~ '[A-Za-z]'", sql)
        self.assertEqual(params[1], "%Methods%")
        self.assertEqual(params[-2:], (10, 5))

    def test_first_paragraph_empty(self) -> None:
        conn = _Conn([])
        with mock.patch.object(reader, "corpus_connection", return_value=conn):
            self.assertIsNone(reader.paper_first_paragraph("paper_1"))


if __name__ == "__main__":
    unittest.main()
