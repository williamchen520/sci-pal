from __future__ import annotations

import unittest

from services.watch.pg_fulltext import _adapt


class WatchFulltextTests(unittest.TestCase):
    def test_adapt_paragraphs(self):
        payload = _adapt(
            {
                "metadata": {"title": "T", "authors": ["A"], "doi": "10.1/x"},
                "paragraphs": [
                    {"text": "Hello", "path": ["Intro"], "sequence": 1}
                ],
            },
            "p1",
            "PMC1.xml",
        )
        self.assertEqual(payload["paper_id"], "p1")
        self.assertEqual(payload["paragraphs"][0]["para_id"], "p1_para_00000")
        self.assertEqual(payload["paragraphs"][0]["text_content"], "Hello")
        self.assertEqual(payload["metadata"]["doi"], "10.1/x")


if __name__ == "__main__":
    unittest.main()
