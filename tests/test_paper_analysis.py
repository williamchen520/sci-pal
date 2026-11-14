"""Single-paper analysis service tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import analysis


class AnalysisTests(unittest.TestCase):
    def test_aggregates_outline_first_and_evidence(self) -> None:
        with mock.patch.object(
            analysis, "_paper_meta", return_value={"title": "T", "doi": "10.1/x"}
        ), mock.patch.object(
            analysis, "paper_outline", return_value=[{"section_path": "Results"}]
        ), mock.patch.object(
            analysis, "paper_first_paragraph", return_value={"para_id": "p1"}
        ), mock.patch.object(
            analysis, "paper_evidence", return_value=[{"sentence_id": "s1"}]
        ), mock.patch.object(analysis, "list_links", return_value=[]), mock.patch.object(analysis, "list_bindings", return_value=[]), mock.patch.object(analysis, "paper_data_flow", return_value={"status": "unbound", "nodes": [], "edges": []}):
            result = analysis.analyze_paper("p1", query="lipid")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["paper"]["title"], "T")
        self.assertEqual(result["first_paragraph"]["para_id"], "p1")
        self.assertEqual(result["evidence"][0]["sentence_id"], "s1")
        self.assertEqual(result["code"]["status"], "not_indexed")

    def test_compact(self) -> None:
        with mock.patch.object(
            analysis, "_paper_meta", return_value={"title": "T"}
        ), mock.patch.object(
            analysis, "paper_outline", return_value=[{"section_path": "R", "section_type": "results"}]
        ), mock.patch.object(
            analysis, "paper_first_paragraph", return_value={"para_id": "p1"}
        ), mock.patch.object(
            analysis, "paper_data_flow", return_value={"status": "ok", "nodes": [1, 2], "edges": [1]}
        ), mock.patch.object(analysis, "list_links", return_value=[]), mock.patch.object(
            analysis, "list_bindings", return_value=[{"library_id": "lib_1"}]
        ):
            result = analysis.analyze_paper("p1", compact=True)
        self.assertEqual(result["outline"], [])
        self.assertEqual(result["outline_summary"]["section_count"], 1)
        self.assertEqual(result["data_flow"]["edges_count"], 1)

    def test_missing_paper(self) -> None:
        with mock.patch.object(analysis, "_paper_meta", return_value={}):
            self.assertIsNone(analysis.analyze_paper("missing"))


if __name__ == "__main__":
    unittest.main()
