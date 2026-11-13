"""R6.1 query worker tests (no network)."""

from __future__ import annotations

import unittest
from unittest import mock

import scripts.rag_worker as worker


class QueryWorkerTests(unittest.TestCase):
    def test_query_worker_sends_evidence(self) -> None:
        job = {
            "job_id": "job_1",
            "rag_id": "code",
            "library_id": "lib_1",
            "job_type": "rag_query",
            "payload": {"query": "normalize_total", "params": {"top_k": 2}},
        }
        response = mock.Mock()
        response.json.return_value = {
            "hits": [
                {
                    "symbol_name": "normalize_total",
                    "path": "a.py",
                    "start_line": 1,
                    "end_line": 2,
                    "snippet": "def normalize_total(): pass",
                    "score": 0.9,
                    "snapshot_id": "snap_1",
                }
            ]
        }
        response.raise_for_status.return_value = None
        with mock.patch("scripts.rag_worker.requests.post", return_value=response), \
             mock.patch("scripts.rag_worker._post") as post:
            worker._execute_query(job, "w")
        body = post.call_args_list[-1].args[1]
        self.assertEqual(body["evidence"][0]["source_path"], "a.py")
        self.assertEqual(body["evidence"][0]["metadata"]["symbol_name"], "normalize_total")


    def test_literature_worker_sends_evidence(self) -> None:
        job = {
            "job_id": "job_lit",
            "rag_id": "literature",
            "library_id": "",
            "job_type": "rag_query",
            "payload": {"query": "normalization", "params": {"top_k": 1}},
        }
        response = mock.Mock()
        response.json.return_value = {
            "evidence": [
                {
                    "paper_id": "paper_1",
                    "para_id": "para_1",
                    "matched_sentences": [{"sentence_id": "s1", "text": "normalized"}],
                    "highlight": [{"score": 0.8}],
                }
            ]
        }
        response.raise_for_status.return_value = None
        with mock.patch("scripts.rag_worker.requests.post", return_value=response), \
             mock.patch("scripts.rag_worker._post") as post:
            worker._execute_literature_query(job, "w")
        body = post.call_args_list[-1].args[1]
        self.assertEqual(body["evidence"][0]["rag_id"], "literature")
        self.assertEqual(body["evidence"][0]["metadata"]["paper_id"], "paper_1")


    def test_docs_worker_sends_evidence(self) -> None:
        job = {
            "job_id": "job_docs",
            "rag_id": "docs",
            "library_id": "",
            "job_type": "rag_query",
            "payload": {"query": "MCP", "params": {"top_k": 1}},
        }
        response = mock.Mock()
        response.json.return_value = {
            "hits": [
                {
                    "doc_id": "doc_1",
                    "title": "Doc",
                    "path": "docs/a.md",
                    "heading": "H",
                    "category": "guide",
                    "text": "MCP content",
                    "score": 0.5,
                }
            ]
        }
        response.raise_for_status.return_value = None
        with mock.patch("scripts.rag_worker.requests.post", return_value=response), \
             mock.patch("scripts.rag_worker._post") as post:
            worker._execute_docs_query(job, "w")
        body = post.call_args_list[-1].args[1]
        self.assertEqual(body["evidence"][0]["rag_id"], "docs")
        self.assertEqual(body["evidence"][0]["source_path"], "docs/a.md")


if __name__ == "__main__":
    unittest.main()
