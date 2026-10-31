"""Adapter B3/B4: hybrid retrieval, optionally with cross-encoder rerank."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.plugins.retriever_contracts import RetrieverAdapter, RetrieverCandidate


class HybridRetriever(RetrieverAdapter):
    name = "retriever-hybrid"
    version = "0.1.0"
    rerank = False

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
        result = self.searcher.search(
            query,
            top_k=int(top_k),
            rerank=self.rerank,
            expand_queries=False,
            filters={"paper_ids": corpus},
            diversify=False,
        )
        rows = result.get("results") or []
        results: List[RetrieverCandidate] = []
        for index, row in enumerate(rows):
            score = row.get("rerank_score", row.get("rrf_score", row.get("score", 0.0)))
            results.append(
                RetrieverCandidate(
                    paper_id=str(row.get("paper_id") or ""),
                    node_id=str(row.get("para_id") or ""),
                    text=str(row.get("text") or ""),
                    score=float(score or 0.0),
                    rank=index + 1,
                )
            )
        return results


class HybridRerankRetriever(HybridRetriever):
    name = "retriever-hybrid-rerank"
    version = "0.1.0"
    rerank = True
