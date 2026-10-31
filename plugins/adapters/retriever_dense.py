"""Adapter B2: dense/Chroma retrieval only."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.plugins.retriever_contracts import RetrieverAdapter, RetrieverCandidate


class DenseRetriever(RetrieverAdapter):
    name = "retriever-dense"
    version = "0.1.0"

    def __init__(self):
        from services.search.hybrid_search import HybridSearch

        self.searcher = HybridSearch()

    def retrieve(
        self,
        query: str,
        *,
        corpus: List[str],
        top_k: int = 10,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[RetrieverCandidate]:
        hits = self.searcher.vector_search(
            query,
            top_k=int(top_k),
            filters={"paper_ids": corpus},
        )
        results: List[RetrieverCandidate] = []
        for index, hit in enumerate(hits):
            metadata = hit.get("metadata") or {}
            results.append(
                RetrieverCandidate(
                    paper_id=str(metadata.get("paper_id") or ""),
                    node_id=str(hit.get("para_id") or ""),
                    text=str(hit.get("text") or ""),
                    score=float(hit.get("score") or 0.0),
                    rank=index + 1,
                )
            )
        return results
