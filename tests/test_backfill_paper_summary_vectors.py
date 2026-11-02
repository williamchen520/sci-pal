from __future__ import annotations

import unittest

from scripts.backfill_paper_summary_vectors import _summary_text


class SummaryTextTests(unittest.TestCase):
    def test_title_only_when_no_body(self):
        self.assertEqual(_summary_text("Introduction", None), "Introduction")

    def test_title_plus_first_sentence(self):
        text = "This is the first sentence. This is the second sentence."
        self.assertEqual(_summary_text("Introduction", text), "Introduction This is the first sentence.")

    def test_empty_title_falls_back(self):
        self.assertEqual(_summary_text("", ""), "Untitled section")


if __name__ == "__main__":
    unittest.main()
