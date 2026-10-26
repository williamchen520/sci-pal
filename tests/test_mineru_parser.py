"""MinerU 4.x adapter: markdown conversion without touching the network."""

from __future__ import annotations

import unittest

from build_db.parsers.mineru_parser import MinerUParser

SAMPLE = """<!-- page 1 of 2 -->

# A study of sepsis

## Abstract
Sepsis is a syndrome.

## Introduction
First paragraph of intro.

Second paragraph of intro.

![Figure 1](images/fig1.png)

<!-- page 2 of 2 -->

## Methods
We used LPS.

## References
Ref one.
"""


class MinerUMarkdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = MinerUParser(cli_path="nonexistent")

    def test_markdown_to_paragraphs(self) -> None:
        paragraphs, figures, title = self.parser._markdown_to_result(SAMPLE, "paper_x")
        self.assertEqual(title, "A study of sepsis")
        self.assertEqual(len(paragraphs), 5)
        self.assertEqual(paragraphs[0]["page_number"], 1)
        self.assertEqual(paragraphs[0]["section_type"], "abstract")
        self.assertEqual(paragraphs[1]["section_type"], "introduction")
        self.assertEqual(paragraphs[-1]["page_number"], 2)
        self.assertEqual(paragraphs[-1]["section_type"], "references")
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["caption"], "Figure 1")
        self.assertIn("fig1.png", figures[0]["image_path"])

    def test_section_classification(self) -> None:
        for heading, expected in (
            ("Abstract", "abstract"),
            ("Materials and methods", "methods"),
            ("Results", "results"),
            ("Discussion", "discussion"),
            ("References", "references"),
            ("Random heading", "body"),
        ):
            self.assertEqual(self.parser._markdown_to_result(f"# T\n\n## {heading}\n\ntext", "p")[0][0]["section_type"], expected)

    def test_stub_when_server_missing(self) -> None:
        result = self.parser.parse("fake.pdf", "p1")
        self.assertEqual(result["metadata"]["parse_status"], "stub")
        self.assertEqual(len(result["paragraphs"]), 1)


if __name__ == "__main__":
    unittest.main()
