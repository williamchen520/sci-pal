"""HTML paper parser tests."""

from __future__ import annotations

import unittest

from services.papers.html_parser import parse_html

HTML = """
<html><head>
<meta name="citation_title" content="A test paper">
<meta name="citation_doi" content="10.1234/test">
<meta name="citation_journal_title" content="Test Journal">
<meta name="citation_author" content="Alice">
</head><body>
<h1>A test paper</h1>
<section data-title="Abstract"><h2>Abstract</h2><p>This is the abstract.</p></section>
<section data-title="Results"><h2>Results</h2><p>First result.</p><p>Second result.</p>
<figure><img src="f1.png"><figcaption>Figure 1. A result.</figcaption></figure>
</section>
<section data-title="Code availability"><h2>Code availability</h2>
<p>Code at <a href="https://github.com/example/repo">GitHub</a> and
<a href="https://doi.org/10.5281/zenodo.123">Zenodo</a>.</p></section>
</body></html>
"""


class HtmlParserTests(unittest.TestCase):
    def test_metadata_and_sections(self) -> None:
        data = parse_html(HTML, source_url="https://example.org/paper")
        self.assertEqual(data["title"], "A test paper")
        self.assertEqual(data["doi"], "10.1234/test")
        self.assertEqual(data["journal"], "Test Journal")
        self.assertIn("This is the abstract.", data["abstract"])
        titles = [section["title"] for section in data["sections"]]
        self.assertIn("Results", titles)
        results = next(section for section in data["sections"] if section["title"] == "Results")
        self.assertEqual(results["paragraphs"], ["First result.", "Second result."])

    def test_figures_and_code_links(self) -> None:
        data = parse_html(HTML)
        self.assertEqual(len(data["figures"]), 1)
        self.assertEqual(data["figures"][0]["image"], "f1.png")
        self.assertIn("https://github.com/example/repo", data["code_links"])
        self.assertIn("https://doi.org/10.5281/zenodo.123", data["code_links"])

    def test_hash_is_stable(self) -> None:
        first = parse_html(HTML)["content_hash"]
        second = parse_html(HTML)["content_hash"]
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
