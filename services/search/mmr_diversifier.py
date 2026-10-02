"""
MMR (Maximal Marginal Relevance) diversifier for retrieval results.
V25.19 - Retrieval optimization

Problem: hybrid search + rerank often returns 5 paragraphs from the same
paper / same section that all say essentially the same thing. The LLM
then gets redundant context and wastes its context window.

Solution: MMR re-ranks candidates to balance relevance (original score)
against diversity (dissimilarity to already-selected items).

Formula:
    MMR(D_i) = λ * Relevance(D_i) - (1-λ) * max_{D_j in S} Similarity(D_i, D_j)

Where:
    λ ∈ [0, 1]: 1.0 = pure relevance (no diversification), 0.5 = balanced
    S: set of already-selected documents
    Similarity: Jaccard overlap of word sets (lightweight, no model needed)

Usage:
    diversifier = MMRDiversifier(lambda_param=0.7)
    diverse = diversifier.diversify(candidates, top_k=6,
                                     text_key="text", score_key="rerank_score")
"""
import re
from typing import List, Dict, Optional, Callable


# V25.21: 停用词表，tokenize 时过滤掉，提升 Jaccard 相似度的敏感度
# （学术段落中这些词大量出现但无区分度，会稀释 Jaccard 相似度）
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "can", "shall", "must", "need", "dare", "ought", "used",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "we", "us", "our", "you", "your", "he", "him", "his", "she", "her",
    "as", "at", "by", "from", "into", "about", "between", "through", "during",
    "before", "after", "above", "below", "up", "down", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "all",
    "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "also", "now", "if", "because", "while", "although", "though",
    "unless", "until", "since", "when", "where", "why", "how", "what",
    "which", "who", "whom", "whose", "whether", "either", "neither",
    "thus", "therefore", "hence", "however", "moreover", "furthermore",
    "nevertheless", "nonetheless", "consequently", "accordingly",
    "fig", "figure", "table", "et", "al", "cf", "e.g", "i.e", "vs",
    "per", "via", "upon", "within", "without", "across", "along",
    "among", "around", "behind", "beside", "beyond", "despite",
    "except", "including", "regarding", "concerning", "following",
}


def _tokenize(text: str) -> set:
    """Tokenize text into a set of lowercase words (min length 2),
    filtering out stop words for more sensitive Jaccard similarity.
    V25.21: 过滤停用词，提升学术段落间相似度的敏感度。"""
    if not text:
        return set()
    tokens = re.findall(r'[a-zA-Z0-9]{2,}', text.lower())
    return {t for t in tokens if t not in _STOP_WORDS}


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity: |A∩B| / |A∪B|. Returns 0 if both empty."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


class MMRDiversifier:
    """
    Re-rank retrieval candidates using Maximal Marginal Relevance.

    Args:
        lambda_param: relevance-diversity balance. 1.0 = pure relevance,
            0.7 = mild diversification (recommended default),
            0.5 = balanced, <0.5 = diversity-heavy.
        min_similarity: if two items are less similar than this, they
            don't penalize each other (avoids over-penalizing unrelated items).
            V25.21: 从 0.15 降到 0.03——学术段落用词差异大，原阈值导致
            MMR 完全不生效（所有 λ 值结果相同）。
        paper_penalty: extra diversity bonus for selecting from a different
            paper_id. Set >0 to encourage cross-paper coverage.
            V25.21: 从 0.05 提升到 0.1，更鼓励跨论文多样性。
    """

    def __init__(self, lambda_param: float = 0.7,
                 min_similarity: float = 0.03,
                 paper_penalty: float = 0.1):
        self.lambda_param = max(0.0, min(1.0, lambda_param))
        self.min_similarity = min_similarity
        self.paper_penalty = paper_penalty

    def diversify(self, candidates: List[Dict], top_k: int = 10,
                  text_key: str = "text",
                  score_key: str = "rerank_score",
                  paper_key: str = "paper_id") -> List[Dict]:
        """
        Re-rank candidates using MMR.

        Args:
            candidates: list of result dicts, must contain text_key and score_key.
            top_k: how many to return.
            text_key: dict key for the text content (for similarity computation).
            score_key: dict key for the relevance score. Falls back to "rrf_score"
                then "score" if the primary key is missing.
            paper_key: dict key for paper_id (for cross-paper diversity bonus).

        Returns:
            Re-ranked list of candidates (same dicts, with added "mmr_score"
            and "mmr_rank" fields), truncated to top_k.
        """
        if not candidates:
            return []
        if top_k >= len(candidates):
            # Not enough candidates to diversify meaningfully; just add scores
            for i, c in enumerate(candidates):
                c["mmr_score"] = c.get(score_key, c.get("rrf_score", c.get("score", 0)))
                c["mmr_rank"] = i + 1
            return candidates

        # Resolve score key with fallbacks
        def get_score(c: Dict) -> float:
            for key in (score_key, "rrf_score", "score"):
                if key in c and c[key] is not None:
                    return float(c[key])
            return 0.0

        # Normalize relevance scores to [0, 1] for stable MMR computation
        scores = [get_score(c) for c in candidates]
        min_s = min(scores) if scores else 0
        max_s = max(scores) if scores else 0
        score_range = max_s - min_s if max_s > min_s else 1.0

        def norm_score(c: Dict) -> float:
            return (get_score(c) - min_s) / score_range

        # Precompute token sets for each candidate
        token_sets = [_tokenize(c.get(text_key, "")) for c in candidates]

        # MMR greedy selection
        selected_indices = []
        remaining = list(range(len(candidates)))

        # First item: highest relevance (no diversity penalty yet)
        first = max(remaining, key=lambda i: norm_score(candidates[i]))
        selected_indices.append(first)
        remaining.remove(first)

        # Subsequent items: balance relevance vs diversity
        while remaining and len(selected_indices) < top_k:
            best_idx = None
            best_mmr = float("-inf")

            for i in remaining:
                rel = norm_score(candidates[i])
                # Max similarity to any already-selected item
                max_sim = 0.0
                for j in selected_indices:
                    sim = _jaccard_similarity(token_sets[i], token_sets[j])
                    if sim > max_sim:
                        max_sim = sim

                # Only penalize if similarity is meaningful
                diversity_penalty = max_sim if max_sim >= self.min_similarity else 0.0

                # Cross-paper diversity bonus
                paper_bonus = 0.0
                if self.paper_penalty > 0 and paper_key in candidates[i]:
                    current_paper = candidates[i].get(paper_key)
                    selected_papers = {candidates[j].get(paper_key)
                                        for j in selected_indices}
                    if current_paper and current_paper not in selected_papers:
                        paper_bonus = self.paper_penalty

                mmr = (self.lambda_param * rel
                       - (1 - self.lambda_param) * diversity_penalty
                       + paper_bonus)

                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i

            if best_idx is not None:
                selected_indices.append(best_idx)
                remaining.remove(best_idx)
            else:
                break

        # Build result in MMR order
        result = []
        for rank, idx in enumerate(selected_indices, 1):
            c = candidates[idx]
            c["mmr_score"] = best_mmr if rank == len(selected_indices) else c.get("mmr_score", 0)
            c["mmr_rank"] = rank
            result.append(c)

        return result

    def diversify_with_diagnostics(self, candidates: List[Dict],
                                    top_k: int = 10,
                                    text_key: str = "text",
                                    score_key: str = "rerank_score",
                                    paper_key: str = "paper_id") -> tuple:
        """
        Same as diversify(), but also returns diagnostic info about the
        diversification process. Used by the retrieval diagnostics module.

        Returns:
            (diverse_results, diagnostics_dict)
        """
        if not candidates:
            return [], {"selected": 0, "original_order": [],
                        "mmr_order": [], "diversity_impact": "no candidates"}

        # Record original order (by score)
        def get_score(c):
            for key in (score_key, "rrf_score", "score"):
                if key in c and c[key] is not None:
                    return float(c[key])
            return 0.0

        original_sorted = sorted(range(len(candidates)),
                                  key=lambda i: -get_score(candidates[i]))
        original_top = original_sorted[:top_k]

        diverse = self.diversify(candidates, top_k, text_key, score_key, paper_key)
        mmr_indices = [candidates.index(c) for c in diverse]

        # Compute diversity metrics
        def avg_pairwise_similarity(indices):
            if len(indices) < 2:
                return 0.0
            token_sets = [_tokenize(candidates[i].get(text_key, "")) for i in indices]
            total = 0.0
            count = 0
            for a in range(len(token_sets)):
                for b in range(a + 1, len(token_sets)):
                    total += _jaccard_similarity(token_sets[a], token_sets[b])
                    count += 1
            return total / count if count > 0 else 0.0

        orig_sim = avg_pairwise_similarity(original_top)
        mmr_sim = avg_pairwise_similarity(mmr_indices)

        # Count unique papers
        def unique_papers(indices):
            return len({candidates[i].get(paper_key) for i in indices
                        if candidates[i].get(paper_key)})

        diagnostics = {
            "lambda_param": self.lambda_param,
            "candidates_total": len(candidates),
            "selected": len(diverse),
            "original_top_indices": original_top,
            "mmr_top_indices": mmr_indices,
            "reorder_count": sum(1 for a, b in zip(original_top, mmr_indices) if a != b),
            "avg_pairwise_similarity_original": round(orig_sim, 4),
            "avg_pairwise_similarity_mmr": round(mmr_sim, 4),
            "diversity_improvement": round(orig_sim - mmr_sim, 4),
            "unique_papers_original": unique_papers(original_top),
            "unique_papers_mmr": unique_papers(mmr_indices),
        }

        return diverse, diagnostics


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    diversifier = MMRDiversifier(lambda_param=0.7)

    # Simulate candidates: 3 from paper A (similar), 3 from paper B (different)
    candidates = [
        {"text": "STAT1 is a transcription factor that mediates interferon signaling",
         "rerank_score": 0.95, "paper_id": "A"},
        {"text": "STAT1 phosphorylation leads to nuclear translocation in interferon response",
         "rerank_score": 0.92, "paper_id": "A"},
        {"text": "STAT1 dimer binds to GAS elements upon interferon stimulation",
         "rerank_score": 0.88, "paper_id": "A"},
        {"text": "JAK inhibitors block cytokine signaling in myelofibrosis treatment",
         "rerank_score": 0.85, "paper_id": "B"},
        {"text": "Single-cell RNA sequencing reveals immune cell heterogeneity in tumors",
         "rerank_score": 0.80, "paper_id": "C"},
        {"text": "Mass cytometry enables high-dimensional immune profiling at single cell level",
         "rerank_score": 0.75, "paper_id": "D"},
    ]

    print("=" * 70)
    print("🎯 MMR Diversifier Test (V25.19)")
    print("=" * 70)

    diverse, diag = diversifier.diversify_with_diagnostics(candidates, top_k=4)

    print(f"\nLambda: {diag['lambda_param']}")
    print(f"Candidates: {diag['candidates_total']}, Selected: {diag['selected']}")
    print(f"Reordered items: {diag['reorder_count']}")
    print(f"Avg pairwise similarity — original: {diag['avg_pairwise_similarity_original']}")
    print(f"Avg pairwise similarity — MMR:      {diag['avg_pairwise_similarity_mmr']}")
    print(f"Diversity improvement: {diag['diversity_improvement']}")
    print(f"Unique papers — original: {diag['unique_papers_original']}")
    print(f"Unique papers — MMR:      {diag['unique_papers_mmr']}")

    print("\n── MMR-ranked results ──")
    for i, c in enumerate(diverse, 1):
        print(f"  [{i}] paper={c['paper_id']} score={c['rerank_score']:.2f} "
              f"mmr_rank={c['mmr_rank']}")
        print(f"      {c['text'][:70]}...")
