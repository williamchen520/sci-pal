"""Tests for bounded citation-graph expansion."""

from __future__ import annotations

import unittest

from services.records.citation_graph import build_citation_graph
from services.records.provenance import stable_record_id


def pid(doi: str, title: str = "") -> dict:
    record = {"doi": doi}
    if title:
        record["title"] = title
    return record


def rid(doi: str) -> str:
    return stable_record_id({"doi": doi})


class FakeFetcher:
    """Minimal source model: identifier -> references / cited_by."""

    def __init__(self, graph: dict, supported: set[str] | None = None) -> None:
        self.graph = graph
        self.supported = supported or {"openalex"}
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, identifier, relation, rows, source):
        self.calls.append((identifier, relation, source))
        if source not in self.supported:
            return None
        return self.graph.get(identifier, {})


GRAPH = {
    "10.1/p1": {"references": [pid("10.1/p2"), pid("10.1/p3")], "cited_by": []},
    "10.1/p2": {"references": [pid("10.1/p4")], "cited_by": [pid("10.1/p1")]},
    "10.1/p3": {"references": [pid("10.1/p2")], "cited_by": []},
    "10.1/p4": {"references": [], "cited_by": [pid("10.1/p2")]},
}


class GraphTests(unittest.TestCase):
    def build(self, seed, **kwargs):
        fetcher = kwargs.pop("fetcher", None) or FakeFetcher(GRAPH)
        return build_citation_graph(seed, fetch_relations=fetcher, **kwargs)

    def test_one_hop_references(self) -> None:
        result = self.build(pid("10.1/p1"), relation="references", sources=["openalex"])
        self.assertEqual(result["depth_completed"], 1)
        self.assertEqual(len(result["nodes"]), 3)
        self.assertEqual(len(result["edges"]), 2)
        self.assertTrue(all(edge["relation"] == "references" for edge in result["edges"]))
        self.assertEqual(result["edges"][0]["from"], rid("10.1/p1"))

    def test_both_keeps_citing_to_cited_direction(self) -> None:
        result = self.build(pid("10.1/p2"), relation="both", sources=["openalex"])
        pairs = {(edge["from"], edge["to"], edge["relation"]) for edge in result["edges"]}
        self.assertIn((rid("10.1/p1"), rid("10.1/p2"), "cited_by"), pairs)
        self.assertIn((rid("10.1/p2"), rid("10.1/p4"), "references"), pairs)

    def test_two_hops(self) -> None:
        result = self.build(pid("10.1/p1"), relation="references", depth=2, sources=["openalex"])
        self.assertEqual(result["depth_completed"], 2)
        self.assertIn(rid("10.1/p4"), {node["record_id"] for node in result["nodes"]})

    def test_observed_by_merges_sources(self) -> None:
        fetcher = FakeFetcher(GRAPH, supported={"openalex", "crossref"})
        result = self.build(
            pid("10.1/p1"), relation="references", sources=["openalex", "crossref"], fetcher=fetcher
        )
        edge = next(e for e in result["edges"] if e["to"] == rid("10.1/p2"))
        self.assertEqual(edge["observed_by"], ["crossref", "openalex"])
        self.assertEqual(sorted(result["sources_succeeded"]), ["crossref", "openalex"])

    def test_unsupported_source_is_skipped_not_failed(self) -> None:
        seed = {"doi": "10.1/p1", "pmid": "28344011"}
        result = self.build(
            seed,
            relation="references",
            sources=["openalex", "pubmed"],
        )
        self.assertIn({"source": "pubmed", "reason": "citation_edges_not_supported"}, result["sources_skipped"])
        self.assertEqual(result["sources_succeeded"], ["openalex"])

    def test_missing_identifier_is_skipped(self) -> None:
        result = self.build(pid("10.1/p1"), relation="references", sources=["pubmed"])
        self.assertEqual(result["sources_skipped"], [{"source": "pubmed", "reason": "missing_source_identifier"}])
        self.assertEqual(len(result["nodes"]), 1)

    def test_max_nodes_truncates(self) -> None:
        result = self.build(
            pid("10.1/p1"), relation="references", sources=["openalex"], max_nodes=2
        )
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncation_reason"], "max_nodes")
        self.assertEqual(len(result["nodes"]), 2)

    def test_max_edges_truncates(self) -> None:
        result = self.build(
            pid("10.1/p1"), relation="references", sources=["openalex"], max_edges=1
        )
        self.assertTrue(result["truncated"])
        self.assertEqual(result["truncation_reason"], "max_edges")
        self.assertEqual(len(result["edges"]), 1)

    def test_source_exception_is_reported(self) -> None:
        def boom(identifier, relation, rows, source):
            raise RuntimeError("upstream down")

        result = self.build(pid("10.1/p1"), relation="references", sources=["openalex"], fetcher=boom)
        self.assertEqual(result["errors"][0]["source"], "openalex")
        self.assertIn("upstream down", result["errors"][0]["error"])
        self.assertEqual(result["sources_succeeded"], [])

    def test_malformed_payload_is_reported(self) -> None:
        def bad(identifier, relation, rows, source):
            return {"references": "nope"}

        result = self.build(pid("10.1/p1"), relation="references", sources=["openalex"], fetcher=bad)
        self.assertIn("Malformed references payload", result["errors"][0]["error"])

    def test_self_loop_ignored(self) -> None:
        def loop(identifier, relation, rows, source):
            return {"references": [pid("10.1/p1")]}

        result = self.build(pid("10.1/p1"), relation="references", sources=["openalex"], fetcher=loop)
        self.assertEqual(result["edges"], [])

    def test_nodes_are_deterministically_ordered(self) -> None:
        result = self.build(pid("10.1/p1"), relation="references", sources=["openalex"])
        ids = [node["record_id"] for node in result["nodes"]]
        self.assertEqual(ids[0], rid("10.1/p1"))
        self.assertEqual(ids[1:], sorted(ids[1:]))

    def test_coverage_notes_present(self) -> None:
        result = self.build(pid("10.1/p1"), relation="references", sources=["openalex"])
        self.assertEqual(len(result["coverage_notes"]), 2)
        self.assertIsNone(result["errors"])

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            build_citation_graph(pid("10.1/p1"), fetch_relations=lambda *a: None, depth=3)
        with self.assertRaises(ValueError):
            build_citation_graph(pid("10.1/p1"), fetch_relations=lambda *a: None, rows=0)
        with self.assertRaises(ValueError):
            build_citation_graph(pid("10.1/p1"), fetch_relations=lambda *a: None, relation="sideways")


if __name__ == "__main__":
    unittest.main()
