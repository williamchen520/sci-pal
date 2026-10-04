"""
Cross-encoder reranker for hybrid search results.
V21.1 - Reranking layer

Takes top-N hybrid results and re-ranks them with a cross-encoder.
Bi-encoder (embedding) compares query/doc independently -> fast but coarse.
Cross-encoder feeds query+doc together -> slower but much more accurate.
"""
from typing import List, Dict

# BGE reranker: good on English academic text, small (~280MB), fast on CPU.
# Alternative: "cross-encoder/ms-marco-MiniLM-L-6-v2"
# V31.74: 直接用本地路径，避免从 HuggingFace 下载
RERANK_MODEL = "D:\\models\\models\\BAAI--bge-reranker-base"


class Reranker:
    def __init__(self, model_name: str = RERANK_MODEL):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, results: List[Dict],
               top_k: int = 5) -> List[Dict]:
        """
        Re-rank hybrid search results with the cross-encoder.

        Args:
            query: user query
            results: list of result dicts from HybridSearch.search()
            top_k: how many to return after reranking
        """
        if not results:
            return []

        # Build (query, document) pairs
        pairs = [(query, r["text"]) for r in results]

        # Cross-encoder scores (higher = more relevant)
        scores = self.model.predict(pairs)

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
