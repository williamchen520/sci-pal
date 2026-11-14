"""N0 detector and router tests."""

from __future__ import annotations

import unittest

from services.imports.detector import detect
from services.imports.router import route


class DetectorTests(unittest.TestCase):
    def test_pdf_magic(self) -> None:
        result = detect("upload.bin", b"%PDF-1.7")
        self.assertEqual(result.source_kind, "pdf")
        self.assertEqual(result.kind, "paper")

    def test_jats(self) -> None:
        result = detect("paper.xml", b"<article><front/><body/>")
        self.assertEqual(result.source_kind, "jats")
        self.assertEqual(result.kind, "paper")

    def test_html(self) -> None:
        result = detect("page.bin", b"<!doctype html><html></html>")
        self.assertEqual(result.source_kind, "html")

    def test_python(self) -> None:
        result = detect("analysis.py", b"print('ok')\n")
        self.assertEqual(result.source_kind, "python")
        self.assertEqual(result.kind, "code")

    def test_r_and_rmd(self) -> None:
        self.assertEqual(detect("figure.R").source_kind, "r")
        self.assertEqual(detect("report.Rmd").source_kind, "rmd")
        self.assertEqual(detect("report.qmd").source_kind, "rmd")

    def test_repo(self) -> None:
        result = detect("https://github.com/org/repo")
        self.assertEqual(result.source_kind, "repo")
        self.assertEqual(result.kind, "code")

    def test_zip(self) -> None:
        result = detect("bundle.zip", b"PK\x03\x04")
        self.assertEqual(result.source_kind, "zip")

    def test_unknown(self) -> None:
        result = detect("notes.txt")
        self.assertEqual(result.source_kind, "unknown")
        self.assertEqual(route(result.source_kind).lane, "quarantine")

    def test_routes(self) -> None:
        self.assertEqual(route("pdf").lane, "paper")
        self.assertEqual(route("html").lane, "paper")
        self.assertEqual(route("python").lane, "code")
        self.assertEqual(route("repo").lane, "code")
        self.assertEqual(route("unknown").lane, "quarantine")


if __name__ == "__main__":
    unittest.main()
