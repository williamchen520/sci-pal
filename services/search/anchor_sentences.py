"""Select anchor sentences from evidence candidates.

Anchors must come from the evidence's own paragraphs. Global sentence FTS is
intentionally not used here: it adds unrelated sentences and inflates highlights.
"""

from __future__ import annotations

import re
from typing import Iterable, List

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "how", "does", "do",
    "what", "which", "who", "why", "when", "where", "this", "that", "these",
    "those", "it", "its", "as", "at", "by", "from", "into", "about",
    "between", "through", "during", "after", "before", "can", "may", "might",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", (text or "").lower())
        if len(token) > 2 and token not in _STOP
    }


def score_sentence(query: str, text: str, *, position: int = 0, existing: bool = False) -> float:
    q = _tokens(query)
    s = _tokens(text)
    if not q:
        return 0.0
    if not s:
        base = 0.0
    else:
        overlap = len(q & s)
        coverage = overlap / len(q)
        density = overlap / max(1, len(s))
        base = 0.7 * coverage + 0.3 * density
    if existing:
        base += 0.25
    if position < 2:
        base += 0.05
    return base


def select_anchors(
    query: str,
    sentences: Iterable[dict],
    *,
    existing: Iterable[dict] = (),
    limit: int = 2,
) -> List[dict]:
    """Return up to ``limit`` anchor sentences, deduplicated by sentence_id."""
    existing_rows = {row.get("sentence_id"): row for row in existing if row.get("sentence_id")}
    rows = []
    seen = set()
    for position, row in enumerate(sentences):
        sid = row.get("sentence_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        item = dict(row)
        item["anchor_score"] = round(
            score_sentence(
                query,
                item.get("text") or "",
                position=position,
                existing=sid in existing_rows,
            ),
            6,
        )
        rows.append(item)
    rows.sort(key=lambda row: (-float(row.get("anchor_score") or 0.0), row.get("sequence") or 0))
    return rows[: max(1, limit)]
