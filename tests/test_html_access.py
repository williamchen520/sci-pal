"""H4 Cell/JS access and Cell adapter tests."""

from __future__ import annotations

import unittest
from pathlib import Path

from services.imports.html_access import (
    HtmlBlocked,
    HtmlJsRequired,
    HtmlPaywalled,
    assert_html_access,
    classify_html_response,
)
from services.papers.html_adapters import detect_publisher
from services.papers.html_parser import parse_html

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "html"


class HtmlAccessTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(classify_html_response(403, "forbidden"), "blocked")
        self.assertEqual(classify_html_response(200, "Just a moment"), "blocked")
        self.assertEqual(classify_html_response(200, "Please enable JavaScript"), "js_required")
        self.assertEqual(classify_html_response(200, "Subscribe to continue"), "paywalled")
        self.assertEqual(classify_html_response(200, "<html>article</html>"), "ok")

    def test_assert_raises(self) -> None:
        with self.assertRaises(HtmlBlocked):
            assert_html_access(403, "blocked")
        with self.assertRaises(HtmlJsRequired):
            assert_html_access(200, "enable JavaScript")
        with self.assertRaises(HtmlPaywalled):
            assert_html_access(200, "subscribe to continue")

    def test_cell_fixture(self) -> None:
        self.assertEqual(detect_publisher("https://www.cell.com/cell-reports/fulltext/x"), "cell")
        data = parse_html(
            (FIXTURES / "cell.html").read_bytes(),
            source_url="https://www.cell.com/cell-reports/fulltext/x",
        )
        self.assertEqual(data["publisher"], "cell")
        self.assertIn("STAR Methods", [s["title"] for s in data["sections"]])
        self.assertIn("Cell abstract", data["abstract"])


if __name__ == "__main__":
    unittest.main()
