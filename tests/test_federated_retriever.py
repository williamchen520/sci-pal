"""P5 federated retrieval merge tests (no database)."""

from __future__ import annotations

import unittest

from services.search.federated_retriever import FederatedHit, FederatedRetriever


def _hit(scope: str, paper_id: str, score: float, **kwargs) -> FederatedHit:
    return FederatedHit(
        scope=scope,
        paper_id=paper_id,
        para_id=f"{paper_id}_p1",
        text="text",
        score=score,
        provenance=[{"library": scope, "paper_id": paper_id, "para_id": f"{paper_id}_p1"}],
        **kwargs,
    )


class FederatedRetrieverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retriever = FederatedRetriever(dsn="unused")

    def test_dedup_by_doi_keeps_best_and_both_libraries(self) -> None:
        rows = self.retriever._merge(
            [
                _hit("main", "paper_a", 0.4, doi="10.1/x"),
                _hit("bench", "doc_a", 0.9, doi="10.1/X"),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["paper_id"], "doc_a")
        self.assertEqual(rows[0]["libraries"], ["bench", "main"])
        self.assertEqual(len(rows[0]["provenance"]), 2)

    def test_dedup_by_work_id(self) -> None:
        rows = self.retriever._merge(
            [
                _hit("main", "paper_a", 0.8, work_id="work_1"),
                _hit("bench", "doc_a", 0.7, work_id="work_1"),
            ]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["paper_id"], "paper_a")

    def test_different_works_stay_separate(self) -> None:
        rows = self.retriever._merge(
            [
                _hit("main", "paper_a", 0.8, doi="10.1/a"),
                _hit("main", "paper_b", 0.7, doi="10.1/b"),
            ]
        )
        self.assertEqual(len(rows), 2)

    def test_order_by_score(self) -> None:
        rows = self.retriever._merge(
            [
                _hit("main", "paper_a", 0.1, doi="10.1/a"),
                _hit("main", "paper_b", 0.9, doi="10.1/b"),
            ]
        )
        self.assertEqual([row["paper_id"] for row in rows], ["paper_b", "paper_a"])

    def test_unknown_scope_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.retriever.search("x", scopes=["nope"])


if __name__ == "__main__":
    unittest.main()
