"""Heuristic evidence sufficiency for abstention.

A question is answerable only when the retrieved evidence both scores well and
shares enough content terms with the question. This is intentionally
conservative: the caller can still decide to answer, but it gives the agent a
signal to say "insufficient evidence" instead of forcing a citation.

Coverage is measured per evidence item, not as a union across the whole result
set. Otherwise ten unrelated documents can collectively "cover" an out-of-domain
question (e.g. France in one paragraph, capital in another).
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List

TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
STOP = {
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "the", "a", "an", "of", "in", "on", "for",
    "to", "and", "or", "with", "by", "from", "does", "do", "did", "can",
    "could", "should", "would", "please", "give", "me", "about", "tell",
}
MIN_SCORE = float(os.environ.get("SCIPAL_SUFFICIENCY_MIN_SCORE", "0.2"))
MIN_COVERAGE = float(os.environ.get("SCIPAL_SUFFICIENCY_MIN_COVERAGE", "0.5"))


def _tokens(text: str) -> set:
    return {t.lower() for t in TOKEN_RE.findall(text or "") if len(t) > 1 and t.lower() not in STOP}


def _minimum_coverage(query_tokens: set) -> float:
    """Short questions need stronger coverage; long questions tolerate more.

    Two-content-word questions are ambiguous ("capital of France"), so both
    words must appear in the top-scoring passage. Longer questions can still be
    answerable when a passage covers only part of the query, so the threshold
    tapers with length.
    """
    size = len(query_tokens)
    if size <= 2:
        return 1.0
    if size == 3:
        return max(MIN_COVERAGE, 0.6)
    if size == 4:
        return max(0.5, MIN_COVERAGE)
    return 0.25


def evaluate(question: str, evidence: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = list(evidence or [])
    query = _tokens(question)
    min_coverage = _minimum_coverage(query)

    top_score = 0.0
    top_item_coverage = 0.0
    max_item_coverage = 0.0
    all_tokens = set()
    for item in items:
        item_tokens = _tokens(item.get("text", ""))
        all_tokens |= item_tokens
        coverage = len(query & item_tokens) / len(query) if query else 0.0
        max_item_coverage = max(max_item_coverage, coverage)
        score = float(item.get("score") or 0.0)
        if score > top_score:
            top_score = score
            top_item_coverage = coverage

    union_coverage = len(query & all_tokens) / len(query) if query else 0.0
    # Short questions are ambiguous and must be covered by one strong passage.
    # Longer questions may legitimately need several passages; for those use
    # union coverage but keep the same score gate.
    effective_coverage = top_item_coverage if len(query) <= 3 else union_coverage
    sufficient = (
        bool(items)
        and top_score >= MIN_SCORE
        and effective_coverage >= min_coverage
    )
    return {
        "sufficient": sufficient,
        "top_score": round(top_score, 4),
        "top_item_coverage": round(top_item_coverage, 4),
        "max_item_coverage": round(max_item_coverage, 4),
        "union_coverage": round(union_coverage, 4),
        "query_coverage": round(effective_coverage, 4),
        "min_coverage": round(min_coverage, 4),
        "thresholds": {"min_score": MIN_SCORE, "min_coverage": min_coverage},
    }
