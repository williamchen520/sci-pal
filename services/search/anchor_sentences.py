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

def select_anchor_window(
    query: str,
    sentences: Iterable[dict],
    *,
    existing: Iterable[dict] = (),
    limit: int = 3,
    window: int = 2,
) -> List[dict]:
    """Pick the best sentence, then its nearest neighbours in the same paragraph."""
    rows = [dict(row) for row in sentences if row.get("sentence_id")]
    if not rows:
        return []
    existing_ids = {row.get("sentence_id") for row in existing if row.get("sentence_id")}
    for row in rows:
        row["anchor_score"] = score_sentence(
            query,
            row.get("text") or "",
            position=int(row.get("sequence") or 0),
            existing=row.get("sentence_id") in existing_ids,
        )
    best = max(rows, key=lambda row: float(row.get("anchor_score") or 0.0))
    same = sorted(
        [row for row in rows if row.get("para_id") == best.get("para_id")],
        key=lambda row: int(row.get("sequence") or 0),
    )
    index = next(i for i, row in enumerate(same) if row.get("sentence_id") == best.get("sentence_id"))
    order = sorted(
        range(len(same)),
        key=lambda i: (abs(i - index), 0 if i <= index else 1),
    )
    chosen = [same[i] for i in order[: max(1, min(limit, 1 + 2 * window))]]
    chosen.sort(key=lambda row: int(row.get("sequence") or 0))
    return chosen

def select_paragraph_windows(
    query: str,
    sentences: Iterable[dict],
    *,
    limit_paragraphs: int = 2,
    window: int = 1,
) -> List[dict]:
    """Select one anchor window per paragraph, then keep the best paragraphs."""
    groups: dict[str, list[dict]] = {}
    for row in sentences:
        if row.get("sentence_id") and row.get("para_id"):
            groups.setdefault(row["para_id"], []).append(dict(row))
    windows = []
    for para_id, rows in groups.items():
        chosen = select_anchor_window(query, rows, limit=3, window=window)
        if chosen:
            score = max(float(row.get("anchor_score") or 0.0) for row in chosen)
            windows.append((score, para_id, chosen))
    windows.sort(key=lambda item: -item[0])
    out = []
    seen = set()
    for _, _, chosen in windows[: max(1, limit_paragraphs)]:
        for row in chosen:
            sid = row.get("sentence_id")
            if sid and sid not in seen:
                seen.add(sid)
                out.append(row)
    return out

def expand_existing_window(
    query: str,
    sentences: Iterable[dict],
    existing: Iterable[dict],
    *,
    window: int = 2,
    limit: int = 8,
) -> List[dict]:
    """Keep existing matched sentences and add same-paragraph neighbours."""
    rows = [dict(row) for row in sentences if row.get("sentence_id")]
    by_id = {row["sentence_id"]: row for row in rows}
    by_para: dict[str, list[dict]] = {}
    for row in rows:
        by_para.setdefault(row.get("para_id"), []).append(row)
    for group in by_para.values():
        group.sort(key=lambda row: int(row.get("sequence") or 0))

    selected = []
    seen = set()
    for anchor in existing:
        sid = anchor.get("sentence_id")
        row = by_id.get(sid)
        if not row:
            continue
        group = by_para.get(row.get("para_id")) or []
        index = next(i for i, item in enumerate(group) if item.get("sentence_id") == sid)
        for pos in range(max(0, index - window), min(len(group), index + window + 1)):
            item = dict(group[pos])
            item["anchor_score"] = round(
                score_sentence(query, item.get("text") or "", position=pos, existing=pos == index),
                6,
            )
            if item["sentence_id"] not in seen:
                seen.add(item["sentence_id"])
                selected.append(item)
        if len(selected) >= limit:
            break
    return selected[: max(1, limit)]
