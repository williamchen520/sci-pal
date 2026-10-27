"""PDF parse pipeline: gate, MinerU fallback, GROBID enrichment, provenance."""

from __future__ import annotations

import unittest

from build_db.parsers.pipeline import (
    GateThresholds,
    PdfParsePipeline,
    body_metrics,
    gate_failure,
    quality_score,
)


def body(text: str, sections: int = 1, citations: int = 0) -> dict:
    paragraphs = [
        {"text": text, "section_level1": f"S{i % sections}" if sections else ""}
        for i in range(3)
    ]
    return {
        "metadata": {"title": "Docling title"},
        "paragraphs": paragraphs,
        "figures": [],
        "tables": [{"id": "t1"}],
        "citations": [{"raw_text": "ref"}] * citations,
    }


class FakeDocling:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def parse(self, pdf_path, paper_id):
        self.calls += 1
        return dict(self.result)


class FakeMineru:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def parse(self, pdf_path, paper_id):
        self.calls += 1
        return dict(self.result)


class FakeGrobid:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def parse(self, pdf_path, paper_id):
        self.calls += 1
        return self.payload


class PipelineTests(unittest.TestCase):
    def test_gate_metrics_and_score(self) -> None:
        weak = body("short text")
        strong = body("long text " * 100, sections=2)
        weak_metrics = body_metrics(weak, pages=2)
        strong_metrics = body_metrics(strong, pages=1)
        self.assertIsNotNone(gate_failure(weak_metrics, GateThresholds()))
        self.assertIsNone(gate_failure(strong_metrics, GateThresholds()))
        self.assertGreater(quality_score(strong_metrics), quality_score(weak_metrics))

    def test_mineru_fallback_when_gate_fails_and_better(self) -> None:
        docling = FakeDocling(body("tiny"))
        mineru = FakeMineru(body("rich text " * 200, sections=3))
        pipeline = PdfParsePipeline(
            docling=docling,
            grobid=None,
            mineru=mineru,
            enable_grobid=False,
            log=lambda *_: None,
        )
        result = pipeline.parse_paper("fake.pdf", "p1")
        self.assertEqual(docling.calls, 1)
        self.assertEqual(mineru.calls, 1)
        self.assertEqual(result["provenance"]["text_engine"], "mineru")
        self.assertIn("mineru_fallback", result["provenance"]["decision"])
        self.assertIn("mineru", result["metadata"]["parse_engine"])

    def test_mineru_not_called_when_gate_passes(self) -> None:
        docling = FakeDocling(body("rich text " * 200, sections=3))
        mineru = FakeMineru(body("other"))
        pipeline = PdfParsePipeline(
            docling=docling,
            grobid=None,
            mineru=mineru,
            enable_grobid=False,
            log=lambda *_: None,
        )
        result = pipeline.parse_paper("fake.pdf", "p1")
        self.assertEqual(mineru.calls, 0)
        self.assertEqual(result["provenance"]["text_engine"], "docling")

    def test_grobid_enriches_metadata_and_citations(self) -> None:
        docling = FakeDocling(body("rich text " * 200, sections=2))
        grobid = FakeGrobid(
            {
                "metadata": {
                    "title": "A proper GROBID title",
                    "authors": ["A", "B"],
                    "journal": "Nature",
                    "doi": "10.1038/s41586-026-0001",
                    "year": 2026,
                    "abstract": "abs",
                },
                "citations": [{"raw_text": "ref1"}, {"raw_text": "ref2"}],
            }
        )
        pipeline = PdfParsePipeline(
            docling=docling, grobid=grobid, enable_mineru=False, log=lambda *_: None
        )
        result = pipeline.parse_paper("fake.pdf", "p1")
        self.assertEqual(result["metadata"]["title"], "A proper GROBID title")
        self.assertEqual(result["metadata"]["journal"], "Nature")
        self.assertEqual(len(result["citations"]), 2)
        self.assertEqual(result["provenance"]["meta_engine"], "grobid")
        self.assertEqual(result["provenance"]["refs_engine"], "grobid")
        self.assertIn("grobid", result["metadata"]["parse_engine"])

    def test_bad_grobid_title_is_rejected(self) -> None:
        docling = FakeDocling(body("rich text " * 200, sections=2))
        grobid = FakeGrobid(
            {"metadata": {"title": "ALL CAPS RUNNING HEADER TITLE", "journal": "J"}, "citations": []}
        )
        pipeline = PdfParsePipeline(
            docling=docling, grobid=grobid, enable_mineru=False, log=lambda *_: None
        )
        result = pipeline.parse_paper("fake.pdf", "p1")
        self.assertEqual(result["metadata"]["title"], "Docling title")


class ProvenancePersistenceTests(unittest.TestCase):
    def test_write_provenance_creates_table_and_row(self) -> None:
        import sqlite3

        from build_db.db_writer import DatabaseWriter

        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        writer = object.__new__(DatabaseWriter)
        writer._write_provenance(
            cursor,
            "p1",
            {
                "text_engine": "docling",
                "meta_engine": "grobid",
                "refs_engine": "grobid",
                "tables_engine": "docling",
                "decision": "primary",
                "metrics": {"chars_per_page": 1200},
            },
        )
        row = conn.execute(
            "SELECT text_engine, meta_engine, refs_engine, decision FROM parse_provenance"
        ).fetchone()
        self.assertEqual(row, ("docling", "grobid", "grobid", "primary"))
        conn.close()


if __name__ == "__main__":
    unittest.main()
