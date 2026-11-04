"""Entity-hit fusion helpers.

Entity FTS hits are a recall signal, not a new retrieval lane. Appending them
after RRF changes the reranker's candidate distribution; boost mode only
re-weights candidates that are already in the fused list.
"""

from __future__ import annotations

import os
from typing import Iterable, List


def _pid(row: dict):
    return row.get("para_id") or row.get("paragraph_id") or row.get("id")


def apply_entity_boost(
    fused: List[dict],
    entity_hits: Iterable[dict],
    *,
    mode: str = "append",
    weight: float = 0.05,
) -> int:
    """Apply entity hits to a fused list and return the affected count.

    modes:
      off    - no-op
      append - legacy: add unseen entity hits to the candidate pool
      boost  - add a small RRF bonus only to hits already in ``fused``
    """
    mode = (mode or "append").strip().lower()
    if mode == "off":
        return 0

    if mode == "append":
        seen = {_pid(row) for row in fused if _pid(row)}
        unique_hits = []
        for hit in entity_hits:
            key = _pid(hit)
            if key and key not in seen:
                seen.add(key)
                unique_hits.append(hit)
        fused.extend(unique_hits)
        return len(unique_hits)

    seen_hits = set()
    unique_hits = []
    for hit in entity_hits:
        key = _pid(hit)
        if key and key not in seen_hits:
            seen_hits.add(key)
            unique_hits.append(hit)

    by_id = {_pid(row): row for row in fused if _pid(row)}
    affected = 0
    for rank, hit in enumerate(unique_hits, 1):
        row = by_id.get(_pid(hit))
        if row is None:
            continue
        row["rrf_score"] = float(row.get("rrf_score") or 0.0) + weight / (60 + rank)
        row["entity_boost"] = float(row.get("entity_boost") or 0.0) + weight / (60 + rank)
        affected += 1
    if affected:
        fused.sort(key=lambda row: float(row.get("rrf_score") or 0.0), reverse=True)
    return affected


def entity_boost_mode() -> str:
    return os.environ.get("SCIPAL_ENTITY_BOOST_MODE", "append").strip().lower()


def entity_boost_weight() -> float:
    try:
        return max(0.0, min(1.0, float(os.environ.get("SCIPAL_ENTITY_BOOST_WEIGHT", "0.05"))))
    except ValueError:
        return 0.05
