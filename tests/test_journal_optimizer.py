"""Journal optimizer wiring tests."""

from __future__ import annotations

import unittest

from build_db.parsers.journal_optimizer import (
    classify_section_journal_aware,
    detect_journal_family,
    optimize_for_journal,
)
from build_db.parsers.pdf_metadata import extract_pdf_title


class JournalOptimizerTests(unittest.TestCase):
    def test_filename_detection(self) -> None:
        self.assertEqual(detect_journal_family({"source_filename": "s41598-026-72616-6.pdf"})[0], "nature")
        self.assertEqual(detect_journal_family({"source_filename": "PIIS0092867426012869.pdf"})[0], "cell")

    def test_cell_headings(self) -> None:
        self.assertEqual(classify_section_journal_aware("Summary", "cell"), "abstract")
        self.assertEqual(classify_section_journal_aware("STAR Methods", "cell"), "methods")
        self.assertEqual(
            classify_section_journal_aware("Quantification and Statistical Analysis", "cell"),
            "methods",
        )

    def test_nature_author_paragraph_is_not_abstract(self) -> None:
        result = {
            "metadata": {"source_filename": "s41598-026-72616-6.pdf"},
            "paragraphs": [
                {"section_type": "body", "section_title": "", "text": "Fang Wang, Qian Liu, Hongqing Chen, Yeke Wu"},
                {"section_type": "body", "section_title": "Introduction", "text": "Intro"},
            ],
        }
        out = optimize_for_journal(result)
        self.assertEqual(out["paragraphs"][0]["section_type"], "body")
        self.assertEqual(out["metadata"]["journal_family"], "nature")

    def test_real_pdf_title_extraction(self) -> None:
        title = extract_pdf_title(r"D:/sciPal/documents/s41598-026-72616-6.pdf")
        self.assertIn("PRRX1", title)
        cell = extract_pdf_title(r"G:/PIIS0092867426012869.pdf")
        self.assertIn("COP1", cell)


if __name__ == "__main__":
    unittest.main()
