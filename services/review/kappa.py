"""Double-screening agreement (Cohen's kappa)."""

from __future__ import annotations

import sqlite3
from typing import Dict, List


def kappa(conn: sqlite3.Connection, project_id: str, stage: str = "title_abstract") -> Dict:
    rows = conn.execute(
        "SELECT paper_id, reviewer, decision FROM screening_decisions "
        "WHERE project_id = ? AND stage = ? AND reviewer != '' "
        "ORDER BY id",
        (project_id, stage),
    ).fetchall()
    latest = {}
    reviewers = set()
    for paper_id, reviewer, decision in rows:
        latest[(paper_id, reviewer)] = decision
        reviewers.add(reviewer)
    reviewers = sorted(reviewers)
    if len(reviewers) < 2:
        return {
            "reviewers": reviewers,
            "pairs": 0,
            "agreement": None,
            "kappa": None,
            "note": "需要至少 2 位 reviewer",
        }

    first, second = reviewers[0], reviewers[1]
    pairs = [
        (paper, latest[(paper, first)], latest[(paper, second)])
        for paper in {key[0] for key in latest}
        if (paper, first) in latest and (paper, second) in latest
    ]
    if not pairs:
        return {"reviewers": reviewers, "pairs": 0, "agreement": None, "kappa": None}

    observed = sum(1 for _, a, b in pairs if a == b) / len(pairs)
    decisions = [decision for _, a, b in pairs for decision in (a, b)]
    categories = set(decisions)
    expected = sum((decisions.count(c) / len(decisions)) ** 2 for c in categories)
    value = 1.0 if expected == 1 else (observed - expected) / (1 - expected)
    return {
        "reviewers": reviewers[:2],
        "pairs": len(pairs),
        "agreement": round(observed, 4),
        "kappa": round(value, 4),
    }
