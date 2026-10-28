"""BibTeX/CSV importer tests."""

from __future__ import annotations

import unittest

from services.review.importers import parse_bibtex, parse_csv, parse_file


class ImporterTests(unittest.TestCase):
    def test_bibtex(self) -> None:
        text = """
@article{key1,
  title = {A Trial of {ICI} Rechallenge},
  doi = {10.1/a},
}
@comment{ignored}
"""
        records = parse_bibtex(text)
        self.assertEqual(len(records), 1)
        self.assertIn("Trial", records[0]["title"])
        self.assertEqual(records[0]["doi"], "10.1/a")

    def test_csv(self) -> None:
        text = "Title,DOI\nTrial A,10.1/a\nTrial B,\n"
        records = parse_csv(text)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1]["title"], "Trial B")

    def test_detect(self) -> None:
        self.assertEqual(parse_file("x.bib", "@article{k,title={T}}")[0]["title"], "T")
        self.assertEqual(parse_file("x.csv", "title,doi\nT,1")[0]["doi"], "1")
        self.assertEqual(parse_file("x.json", "{}"), [])


if __name__ == "__main__":
    unittest.main()
