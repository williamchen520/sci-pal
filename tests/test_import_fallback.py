"""H3 HTML failure PDF fallback tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.imports.html_quality import QualityRejected
from services.imports.paper_lane import PaperLaneAdapter


def _item(html: Path, pdf: Path | None = None) -> dict:
    return {
        "import_id": "imp_1",
        "item_id": "item_0001",
        "source_kind": "html",
        "staged_path": str(html),
        "source_uri": "https://example/bad",
        "fallback_path": str(pdf) if pdf else "",
    }


class FallbackTests(unittest.TestCase):
    def test_bad_html_falls_back_to_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "bad.html"
            html.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
            pdf = Path(tmp) / "paper.pdf"
            pdf.write_bytes(b"%PDF-1.7")
            with mock.patch(
                "services.imports.paper_lane.parse_and_store",
                return_value={"paper_id": "paper_pdf"},
            ), mock.patch(
                "services.imports.paper_lane.build_for_paper",
                return_value={"sentences": 10},
            ), mock.patch(
                "services.imports.paper_lane.session.set_item_parsed"
            ) as parsed:
                status = PaperLaneAdapter(build=True).process(_item(html, pdf))
        self.assertEqual(status, "built")
        self.assertEqual(parsed.call_args.args[2]["fallback_from"], "html")

    def test_bad_html_without_pdf_quarantines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "bad.html"
            html.write_text("<html><body><p>x</p></body></html>", encoding="utf-8")
            with mock.patch(
                "services.imports.paper_lane.session.set_item_parsed"
            ):
                with self.assertRaises(QualityRejected):
                    PaperLaneAdapter(build=True).process(_item(html))

    def test_good_html_does_not_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html = Path(tmp) / "good.html"
            sections = "".join(
                f"<section data-title='S{i}'><p>{'x' * 220}</p><p>{'y' * 220}</p></section>"
                for i in range(3)
            )
            html.write_text(
                "<html><head><meta name='citation_title' content='A good title for testing'>"
                "<meta name='citation_doi' content='10.1/x'></head><body>"
                f"<div id='Abs1-content'>{'a' * 150}</div>{sections}</body></html>",
                encoding="utf-8",
            )
            with mock.patch(
                "services.imports.paper_lane.session.set_item_parsed"
            ), mock.patch(
                "services.imports.paper_lane.parse_and_store"
            ) as pdf_parse:
                status = PaperLaneAdapter(build=False).process(
                    _item(html, Path(tmp) / "missing.pdf")
                )
        self.assertEqual(status, "parsed")
        pdf_parse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
