"""H1 publisher HTML adapter tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from services.papers.html_adapters import detect_publisher
from services.papers.html_parser import parse_html

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "html"


class HtmlAdapterTests(unittest.TestCase):
    def test_detect(self) -> None:
        self.assertEqual(detect_publisher("https://www.nature.com/articles/s41598-1"), "nature")
        self.assertEqual(detect_publisher("https://pmc.ncbi.nlm.nih.gov/articles/PMC1/"), "pmc")
        self.assertEqual(detect_publisher("https://example.org/a"), "other")

    def test_nature_sections(self) -> None:
        data = parse_html(
            (FIXTURES / "nature.html").read_bytes(),
            source_url="https://www.nature.com/articles/s41598-026-00000-0",
        )
        self.assertEqual(data["publisher"], "nature")
        self.assertEqual([s["title"] for s in data["sections"]], ["Abstract", "Introduction", "Results"])
        self.assertIn("Nature abstract", data["abstract"])

    def test_pmc_sections(self) -> None:
        data = parse_html(
            (FIXTURES / "pmc.html").read_bytes(),
            source_url="https://pmc.ncbi.nlm.nih.gov/articles/PMC1/",
        )
        self.assertEqual(data["publisher"], "pmc")
        self.assertEqual([s["title"] for s in data["sections"]], ["Abstract", "Introduction", "Results"])
        self.assertIn("PMC abstract", data["abstract"])


if __name__ == "__main__":
    unittest.main()
