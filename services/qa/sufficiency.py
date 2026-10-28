"""Heuristic evidence sufficiency for abstention.

A question is answerable only when the retrieved evidence both scores well and
shares enough content terms with the question. This is intentionally
conservative: the caller can still decide to answer, but it gives the agent a
signal to say "insufficient evidence" instead of forcing a citation.
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


def evaluate(question: str, evidence: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = list(evidence or [])
    query = _tokens(question)
    text_tokens = set()
    top_score = 0.0
    for item in items:
        text_tokens |= _tokens(item.get("text", ""))
        top_score = max(top_score, float(item.get("score") or 0.0))
    coverage = len(query & text_tokens) / len(query) if query else 0.0
    sufficient = bool(items) and top_score >= MIN_SCORE and coverage >= MIN_COVERAGE
    return {
        "sufficient": sufficient,
        "top_score": round(top_score, 4),
        "query_coverage": round(coverage, 4),
        "thresholds": {"min_score": MIN_SCORE, "min_coverage": MIN_COVERAGE},
    }
