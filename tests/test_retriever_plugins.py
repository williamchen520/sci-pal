"""M2 retriever adapter tests (no model loading)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.adapters.retriever_bm25 import BM25Retriever
from services.plugins import PluginRegistry, PluginRunner


class RetrieverPluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = Path(self.tmp.name) / "runs.jsonl"
        self.registry = PluginRegistry().load()

    def test_retriever_plugins_are_registered(self) -> None:
        ids = [item["id"] for item in self.registry.list_plugins()]
        for plugin_id in (
            "retriever-bm25",
            "retriever-dense",
            "retriever-hybrid",
            "retriever-hybrid-rerank",
        ):
            self.assertIn(plugin_id, ids)

    def test_bm25_respects_corpus_and_ranks(self) -> None:
        corpus = ["paper_PMC12707946_2d3bcc67", "paper_PMC13616637_ab84d6de_xml"]
        candidates = BM25Retriever().retrieve(
            "ICI rechallenge hepatocellular carcinoma", corpus=corpus, top_k=5
        )
        self.assertTrue(candidates)
        self.assertTrue(all(item.paper_id in corpus for item in candidates))
        self.assertEqual([item.rank for item in candidates], list(range(1, len(candidates) + 1)))

    def test_runner_validates_retriever_output(self) -> None:
        runner = PluginRunner(self.registry, run_log=self.log)
        run = runner.run(
            "retriever-bm25",
            {
                "query": "ICI rechallenge",
                "corpus": ["paper_PMC12707946_2d3bcc67"],
                "top_k": 3,
            },
            dataset_hash="sha256:test",
        )
        self.assertIn("candidates", run.output)
        self.assertTrue(self.log.exists())


if __name__ == "__main__":
    unittest.main()
