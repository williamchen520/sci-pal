"""Evidence selection with soft per-paper caps and MMR-style diversity.

No production caller is wired yet; this is evaluated offline first.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from services.search.dedup import jaccard, normalize_text, shingles


def _score(item: Dict[str, Any], score_key: str) -> float:
    value = item.get(score_key)
    if value is None:
        value = item.get("rerank_score", item.get("rrf_score", item.get("score", 0.0)))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _paper(item: Dict[str, Any], paper_key: str) -> Optional[str]:
    value = item.get(paper_key)
    return str(value) if value else None


def select_diverse(
    items: Sequence[Dict[str, Any]],
    *,
    top_k: int = 10,
    max_per_paper: Optional[int] = 3,
    min_distinct_papers: int = 5,
    lambda_: float = 0.75,
    text_key: str = "text",
    paper_key: str = "paper_id",
    score_key: str = "score",
) -> List[Dict[str, Any]]:
    """Greedy MMR selection with a soft per-paper cap.

    Relevance is min-max normalized per query. Similarity is word 3-gram
    Jaccard. The cap is soft: if the pool cannot reach ``min_distinct_papers``,
    the function returns what it can and the caller reports the shortfall.
    """
    unique: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_text = set()
    for item in items:
        identity = item.get("sentence_id") or item.get("para_id") or item.get("text")
        if identity and identity in seen_ids:
            continue
        normalized = normalize_text(str(item.get(text_key) or ""))
        if normalized and normalized in seen_text:
            continue
        if identity:
            seen_ids.add(identity)
        if normalized:
            seen_text.add(normalized)
        unique.append(item)
    if not unique or top_k <= 0:
        return []

    scores = [_score(item, score_key) for item in unique]
    low, high = min(scores), max(scores)
    span = high - low
    normalized_scores = [((score - low) / span if span else 1.0) for score in scores]
    signatures = [shingles(str(item.get(text_key) or "")) for item in unique]

    selected: List[Dict[str, Any]] = []
    selected_sigs: List[set] = []
    counts: Dict[str, int] = {}
    remaining = set(range(len(unique)))

    while remaining and len(selected) < top_k:
        best_index = None
        best_value = -math.inf
        for index in remaining:
            paper = _paper(unique[index], paper_key)
            if max_per_paper is not None and paper and counts.get(paper, 0) >= max_per_paper:
                continue
            similarity = max((jaccard(signatures[index], sig) for sig in selected_sigs), default=0.0)
            value = lambda_ * normalized_scores[index] - (1 - lambda_) * similarity
            if value > best_value:
                best_value = value
                best_index = index
        if best_index is None:
            break
        item = unique[best_index]
        selected.append(item)
        selected_sigs.append(signatures[best_index])
        paper = _paper(item, paper_key)
        if paper:
            counts[paper] = counts.get(paper, 0) + 1
        remaining.remove(best_index)

    # min_distinct_papers is a diagnostic, not a reason to hide the shortfall.
    return selected


def diversity_report(selected: Sequence[Dict[str, Any]], *, paper_key: str = "paper_id") -> dict:
    papers = [p for p in (_paper(item, paper_key) for item in selected) if p]
    counts: Dict[str, int] = {}
    for paper in papers:
        counts[paper] = counts.get(paper, 0) + 1
    return {
        "selected": len(selected),
        "distinct_papers": len(counts),
        "max_hits_per_paper": max(counts.values()) if counts else 0,
    }
