"""Paragraph citation helper tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.qa.citations import paragraph_citation


class CitationTests(unittest.TestCase):
    def test_paragraph_citation(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE sentences (sentence_id TEXT, para_id TEXT, sequence INTEGER)"
            )
            conn.execute("INSERT INTO sentences VALUES ('s1','p1',1)")
            conn.execute("INSERT INTO sentences VALUES ('s2','p1',2)")
            conn.commit()
            conn.close()
            result = paragraph_citation("p1", db)
        self.assertEqual(result["paragraph_id"], "p1")
        self.assertEqual(result["sentence_ids"], ["s1", "s2"])

    def test_empty(self) -> None:
        self.assertEqual(paragraph_citation(""), {})

    def test_build_sources_adds_paragraph_ids(self) -> None:
        from unittest import mock

        from services.qa.qa_service import QAService

        service = object.__new__(QAService)
        retrieval = {
            "paragraphs": [
                {"para_id": "p1", "paper_id": "paper", "text": "body"},
            ]
        }
        citations = [{"type": "P", "num": 1, "raw": "[P1]"}]
        with mock.patch(
            "services.qa.qa_service.paragraph_citation",
            return_value={"paragraph_id": "p1", "sentence_ids": ["s1", "s2"]},
        ):
            sources = service._build_sources(retrieval, citations)
        self.assertEqual(sources["paragraphs"][0]["paragraph_id"], "p1")
        self.assertEqual(sources["paragraphs"][0]["sentence_ids"], ["s1", "s2"])
