"""Sentence-level source-aware FTS tests."""

from __future__ import annotations

import unittest

from services.search.sentence_fts import SentenceFTS, SentenceHit


class _FakePG:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def execute(self, sql, params=None):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        pass


def _row(**overrides):
    row = {
        "sentence_id": "s1",
        "paper_id": "p1",
        "para_id": "para1",
        "section_id": "sec1",
        "text": "text",
        "source_type": "xml",
        "page": None,
        "bbox": None,
        "source_path": "/article/body/sec[1]/p[1]#sentence-1",
        "title": "T",
        "rank": 0.5,
    }
    row.update(overrides)
    return row


class SentenceFTSTests(unittest.TestCase):
    def test_xml_hit_keeps_xpath_and_null_coords(self) -> None:
        fake = _FakePG([_row()])
        hits = SentenceFTS(connector=lambda: fake).search("x", source_type="xml")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source_path, "/article/body/sec[1]/p[1]#sentence-1")
        self.assertIsNone(hits[0].page)
        self.assertIn("source_type = %s", fake.sql)
        self.assertEqual(fake.params[1], "xml")

    def test_pdf_hit_keeps_page_bbox(self) -> None:
        fake = _FakePG([_row(source_type="pdf", page=5, bbox="1,2,3,4", source_path="/paragraphs/34")])
        hit = SentenceFTS(connector=lambda: fake).search("x", source_type="pdf")[0]
        self.assertEqual(hit.page, 5)
        self.assertEqual(hit.bbox, "1,2,3,4")

    def test_aggregate_keeps_best_sentence_per_paragraph(self) -> None:
        hits = [
            SentenceHit("s1", "p1", "para1", "sec1", "low", "pdf", 1, "b", "/p1", "T", 0.1),
            SentenceHit("s2", "p1", "para1", "sec1", "high", "pdf", 1, "b", "/p1", "T", 0.9),
        ]
        result = SentenceFTS(connector=lambda: _FakePG([])).aggregate_by_paragraph(hits)
        self.assertEqual(result[0]["text"], "high")
        self.assertEqual(result[0]["sentence_ids"], ["s1", "s2"])


if __name__ == "__main__":
    unittest.main()
