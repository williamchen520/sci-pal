"""Near-duplicate suppression for retrieval candidates.

The rule is deliberately conservative:

* exact duplicates (same sentence/paragraph or same normalized text) are removed;
* near-duplicates are compared only inside the same paper;
* the highest-scoring copy is kept;
* different papers are never collapsed unless the text is exactly identical.

This keeps document-level diversity from destroying evidence coverage.
"""

from __future__ import annotations

import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_WORD_RE = re.compile(r"[a-z0-9]+")
_WS_RE = re.compile(r"\s+")

DEFAULT_THRESHOLD = 0.90


def normalize_text(text: str) -> str:
    """Lowercase, strip punctuation noise, collapse whitespace."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text.lower()).strip()


def shingles(text: str, n: int = 3) -> Set[str]:
    """Word n-gram shingles for a stable, cheap similarity signal."""
    words = _WORD_RE.findall(normalize_text(text))
    if not words:
        return set()
    if len(words) < n:
        return {" ".join(words)}
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def _score(item: Dict[str, Any], score_key: str) -> float:
    value = item.get(score_key)
    if value is None:
        value = item.get("rerank_score", item.get("rrf_score", item.get("score", 0.0)))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _paper_id(item: Dict[str, Any], paper_key: str) -> Optional[str]:
    value = item.get(paper_key)
    return str(value) if value else None


def _identity_keys(item: Dict[str, Any], id_keys: Sequence[str]) -> Tuple[str, ...]:
    values = []
    for key in id_keys:
        value = item.get(key)
        if value:
            values.append(f"{key}:{value}")
    return tuple(values)


def suppress_near_duplicates(
    items: Iterable[Dict[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    text_key: str = "text",
    paper_key: str = "paper_id",
    id_keys: Sequence[str] = ("sentence_id", "para_id"),
    score_key: str = "score",
    max_per_paper: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Return candidates with exact and same-paper near duplicates removed.

    ``threshold <= 0`` disables near-duplicate suppression; exact duplicates are
    still removed. The result is sorted by score descending, with original order
    as a stable tie-breaker.
    """
    ordered = list(items)
    if not ordered:
        return []

    ordered.sort(key=lambda item: -_score(item, score_key))
    kept: List[Dict[str, Any]] = []
    seen_ids: Set[Tuple[str, ...]] = set()
    seen_text: Set[str] = set()
    by_paper: Dict[str, List[Tuple[Set[str], Dict[str, Any]]]] = {}
    per_paper_count: Dict[str, int] = {}

    for item in ordered:
        identity = _identity_keys(item, id_keys)
        if identity:
            if identity in seen_ids:
                continue
            seen_ids.add(identity)

        text = str(item.get(text_key) or "")
        normalized = normalize_text(text)
        if normalized and normalized in seen_text:
            continue
        if normalized:
            seen_text.add(normalized)

        paper = _paper_id(item, paper_key)
        if max_per_paper is not None and paper:
            if per_paper_count.get(paper, 0) >= max_per_paper:
                continue

        if threshold > 0 and paper:
            signature = shingles(text)
            candidates = by_paper.setdefault(paper, [])
            if any(jaccard(signature, kept_sig) >= threshold for kept_sig, _ in candidates):
                continue
            candidates.append((signature, item))

        if max_per_paper is not None and paper:
            per_paper_count[paper] = per_paper_count.get(paper, 0) + 1
        kept.append(item)

    return kept


def threshold_from_env(default: float = 0.0) -> float:
    raw = os.environ.get("SCIPAL_NEAR_DUP_THRESHOLD")
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if math.isnan(value) or value < 0:
        return default
    return value
