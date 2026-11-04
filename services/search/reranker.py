"""
Cross-encoder reranker for hybrid search results.
V21.1 - Reranking layer

Takes top-N hybrid results and re-ranks them with a cross-encoder.
Bi-encoder (embedding) compares query/doc independently -> fast but coarse.
Cross-encoder feeds query+doc together -> slower but much more accurate.
"""
from typing import List, Dict
import os

from config.paths import RERANK_MODEL


class Reranker:
    def __init__(self, model_name: str = RERANK_MODEL):
        from sentence_transformers import CrossEncoder

        device = os.environ.get("SCIPAL_RERANK_DEVICE", "").strip()
        if not device:
            try:
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:  # noqa: BLE001
                device = "cpu"
        self.device = device
        self.model = CrossEncoder(model_name, device=device)

    def rerank(self, query: str, results: List[Dict],
               top_k: int = 5, batch_size: int = 32) -> List[Dict]:
        """
        Re-rank hybrid search results with the cross-encoder.

        Args:
            query: user query
            results: list of result dicts from HybridSearch.search()
            top_k: how many to return after reranking
        """
        if not results:
            return []

        # Bound CPU cost: long paragraphs are truncated before the cross-encoder.
        try:
            max_items = max(1, int(os.environ.get("SCIPAL_RERANK_MAX_ITEMS", "40")))
            max_chars = max(80, int(os.environ.get("SCIPAL_RERANK_MAX_CHARS", "512")))
        except ValueError:
            max_items, max_chars = 40, 512
        results = results[:max_items]
        pairs = [(query, (r.get("text") or "")[:max_chars]) for r in results]

        # Cross-encoder scores (higher = more relevant)
        scores = self.model.predict(pairs, batch_size=batch_size)

        for r, score in zip(results, scores):
            r["rerank_score"] = float(score)

        # Sort by cross-encoder score
        reranked = sorted(results, key=lambda x: -x["rerank_score"])

        return reranked[:top_k]


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from services.search.hybrid_search import HybridSearch

    print("=" * 60)
    print("🔄 Hybrid Search + Cross-Encoder Rerank Test")
    print("=" * 60)

    query = "How does STAT1 regulate immune response?"
    print(f"\nQuery: {query}\n")

    # Step 1: hybrid retrieval (recall-oriented, top 20)
    searcher = HybridSearch()
    hybrid = searcher.search(query, top_k=20)
    print(f"Hybrid candidates: {len(hybrid['results'])} "
          f"({hybrid['variants']} variants, {hybrid['retrieval_lists']} lists fused)\n")

    # Step 2: cross-encoder rerank (precision-oriented, top 5)
    print("Reranking with cross-encoder...\n")
    reranker = Reranker()
    final = reranker.rerank(query, hybrid["results"], top_k=5)

    print(f"Top {len(final)} after rerank:\n")
    for i, r in enumerate(final):
        preview = r["text"][:140].replace("\n", " ")
        print(f"  [{i+1}] rerank={r['rerank_score']:.3f}  "
              f"rrf={r['rrf_score']:.4f}")
        print(f"      {preview}...\n")
