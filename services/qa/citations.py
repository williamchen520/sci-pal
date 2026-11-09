"""Paragraph-level citation metadata for QA sources."""

from __future__ import annotations

from typing import Dict, List

from services.db.pg_pool import pg_connection


def paragraph_citation(para_id: str, db_path=None) -> Dict[str, object]:
    if not para_id:
        return {}
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT sentence_id FROM sentences WHERE para_id = %s ORDER BY sequence",
            (para_id,),
        ).fetchall()
    finally:
        pg.close()
    return {
        "paragraph_id": para_id,
        "sentence_ids": [row["sentence_id"] for row in rows],
    }


def fallback_citations(paragraph_count: int, limit: int = 3) -> List[Dict[str, object]]:
    """Deterministic citation IDs when the model omitted them."""
    count = min(max(paragraph_count, 0), limit)
    return [
        {"type": "P", "num": index, "raw": f"[P{index}]", "fallback": True}
        for index in range(1, count + 1)
    ]
