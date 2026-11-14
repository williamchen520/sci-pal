"""H2 HTML quality gate tests."""

from __future__ import annotations

import unittest

from services.imports.html_quality import evaluate_html


def _good() -> dict:
    return {
        "title": "A sufficiently descriptive paper title",
        "doi": "10.1038/test",
        "abstract": "A" * 150,
        "sections": [
            {"title": "Introduction", "paragraphs": ["B" * 220] * 2},
            {"title": "Results", "paragraphs": ["C" * 220] * 2},
            {"title": "Discussion", "paragraphs": ["D" * 220]},
        ],
    }


class HtmlQualityTests(unittest.TestCase):
    def test_good_payload_passes(self) -> None:
        result = evaluate_html(_good())
        self.assertTrue(result.ok, result.issues)
        self.assertEqual(result.metrics["sections"], 3)

    def test_missing_title_rejected(self) -> None:
        payload = _good()
        payload["title"] = ""
        self.assertFalse(evaluate_html(payload).ok)

    def test_short_abstract_rejected(self) -> None:
        payload = _good()
        payload["abstract"] = "short"
        self.assertFalse(evaluate_html(payload).ok)

    def test_too_few_sections_rejected(self) -> None:
        payload = _good()
        payload["sections"] = payload["sections"][:1]
        self.assertFalse(evaluate_html(payload).ok)

    def test_too_few_paragraphs_rejected(self) -> None:
        payload = _good()
        payload["sections"] = [{"title": "Only", "paragraphs": ["x"]}]
        self.assertFalse(evaluate_html(payload).ok)

    def test_missing_doi_is_warning(self) -> None:
        payload = _good()
        payload["doi"] = ""
        result = evaluate_html(payload)
        self.assertTrue(result.ok)
        self.assertIn("doi missing", result.warnings)


if __name__ == "__main__":
    unittest.main()
