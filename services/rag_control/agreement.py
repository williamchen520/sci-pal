"""R11: double-review agreement and Cohen's kappa."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from services.db.pg_pool import core_connection


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    if len(a) != len(b) or not a:
        return None
    labels = sorted(set(a) | set(b))
    total = len(a)
    observed = sum(1 for left, right in zip(a, b) if left == right) / total
    expected = 0.0
    for label in labels:
        p_a = sum(1 for value in a if value == label) / total
        p_b = sum(1 for value in b if value == label) / total
        expected += p_a * p_b
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return round((observed - expected) / (1.0 - expected), 4)


def agreement(multi_run_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        exists = pg.execute(
            "SELECT 1 FROM rag_multi_queries WHERE multi_run_id=%s", (multi_run_id,)
        ).fetchone()
        if not exists:
            return None
        rows = pg.execute(
            "SELECT rag_id, decision, decided_by, created_at FROM rag_adjudications "
            "WHERE multi_run_id=%s AND rag_id <> '*' ORDER BY created_at",
            (multi_run_id,),
        ).fetchall()
    finally:
        pg.close()
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        latest.setdefault(row["rag_id"], {})[row["decided_by"]] = row["decision"]
    reviewers = sorted({name for ratings in latest.values() for name in ratings})
    pairwise = []
    disagreements = []
    for left, right in combinations(reviewers, 2):
        items = sorted(
            rag_id
            for rag_id, ratings in latest.items()
            if left in ratings and right in ratings
        )
        if not items:
            continue
        a = [latest[rag_id][left] for rag_id in items]
        b = [latest[rag_id][right] for rag_id in items]
        pairwise.append(
            {
                "reviewer_a": left,
                "reviewer_b": right,
                "items": len(items),
                "agreement": round(sum(1 for x, y in zip(a, b) if x == y) / len(items), 4),
                "kappa": cohen_kappa(a, b),
            }
        )
        for rag_id, x, y in zip(items, a, b):
            if x != y:
                disagreements.append({"rag_id": rag_id, "reviewer_a": left, "a": x, "reviewer_b": right, "b": y})
    return {
        "multi_run_id": multi_run_id,
        "reviewer_count": len(reviewers),
        "reviewers": reviewers,
        "pairwise": pairwise,
        "disagreements": disagreements,
        "sufficient": bool(pairwise) and all(item["kappa"] is not None for item in pairwise),
    }
