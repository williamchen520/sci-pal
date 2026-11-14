"""N0 lane adapter tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.imports.code_lane import CodeLaneAdapter
from services.imports.paper_lane import AdapterUnavailable, PaperLaneAdapter


class LaneTests(unittest.TestCase):
    def _item(self, path: Path, kind: str) -> dict:
        return {
            "import_id": "imp_1",
            "item_id": "i1",
            "source_kind": kind,
            "staged_path": str(path),
            "source_uri": str(path),
        }

    def test_jats_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.xml"
            path.write_text(
                "<article article-type='review'><front><article-title>T</article-title>"
                "<journal-title>J</journal-title></front><body><sec sec-type='results'>"
                "<title>Results</title><p>Body</p></sec></body></article>",
                encoding="utf-8",
            )
            with mock.patch(
                "services.imports.paper_lane.session.set_item_parsed"
            ) as parsed:
                status = PaperLaneAdapter().process(self._item(path, "jats"))
        self.assertEqual(status, "parsed")
        self.assertEqual(parsed.call_args.args[2]["sections"][0]["title"], "Results")

    def test_html_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "page.html"
            path.write_text(
                "<html><body><section><h2>Results</h2><p>X</p></section></body></html>",
                encoding="utf-8",
            )
            with mock.patch(
                "services.imports.paper_lane.session.set_item_parsed"
            ) as parsed:
                status = PaperLaneAdapter().process(self._item(path, "html"))
        self.assertEqual(status, "parsed")
        self.assertTrue(parsed.called)

    def test_pdf_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.pdf"
            path.write_bytes(b"%PDF-1.7")
            with self.assertRaises(AdapterUnavailable):
                PaperLaneAdapter().process(self._item(path, "pdf"))

    def test_python_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.py"
            path.write_text("def f():\n    return 1\n", encoding="utf-8")
            with mock.patch(
                "services.imports.code_lane.session.set_item_parsed"
            ) as parsed:
                status = CodeLaneAdapter().process(self._item(path, "python"))
        self.assertEqual(status, "parsed")
        self.assertGreater(parsed.call_args.args[2]["unit_count"], 0)


if __name__ == "__main__":
    unittest.main()
