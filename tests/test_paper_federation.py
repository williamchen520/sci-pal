"""Paper-level federation tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.papers import federation


class FederationTests(unittest.TestCase):
    def test_groups_sources_without_merging(self) -> None:
        sources = [
            {"source_id": "s1", "source_kind": "html", "source_uri": "u1"},
            {"source_id": "s2", "source_kind": "pdf", "source_uri": "u2"},
        ]
        with mock.patch.object(federation, "_paper_meta", return_value={"title": "T"}), mock.patch.object(
            federation, "list_sources", return_value=sources
        ), mock.patch.object(
            federation, "html_native", return_value={"section_count": 2, "paragraph_count": 3}
        ), mock.patch.object(
            federation, "pdf_native", return_value={"page_count": 4, "paragraph_count": 5}
        ):
            result = federation.federated_paper("p1")
        self.assertEqual(result["source_kinds"], ["html", "pdf"])
        self.assertFalse(result["policy"]["merge_scores"])
        self.assertEqual(result["groups"][0]["native"]["section_count"], 2)

    def test_filter(self) -> None:
        sources = [{"source_id": "s1", "source_kind": "html"}]
        with mock.patch.object(federation, "_paper_meta", return_value={"title": "T"}), mock.patch.object(
            federation, "list_sources", return_value=sources
        ), mock.patch.object(
            federation, "html_native", return_value={"section_count": 2, "paragraph_count": 3}
        ):
            result = federation.federated_paper("p1", source_kinds=["jats"])
        self.assertEqual(result["groups"], [])

    def test_missing(self) -> None:
        with mock.patch.object(federation, "_paper_meta", return_value={}):
            self.assertIsNone(federation.federated_paper("p1"))


if __name__ == "__main__":
    unittest.main()
