"""PostgreSQL search/interrogate adapter for claims."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.claims import pg_read, retrieval
from services.db.pg_pool import pg_connection


def search_candidates(
    claim_id: str,
    direction: str = "support",
    limit: int = 8,
    *,
    retriever=None,
    llm_client=None,
) -> List[Dict[str, Any]]:
    claim = pg_read.get_claim(claim_id)
    if not claim:
        raise ValueError("claim not found")
    queries = retrieval.build_queries(claim["claim_text"], claim.get("qualifiers") or {})
    query = queries.get("refute" if direction == "oppose" else "support") or queries["support"]
    if not query:
        return []
    corpus = [paper_id for paper_id in (claim.get("corpus") or []) if paper_id]

    pg = pg_connection()
    try:
        sql = (
            "SELECT s.sentence_id, s.paper_id, s.text AS quote, p.title AS paper_title, "
            "ts_rank_cd(s.search_vector, websearch_to_tsquery('english', %s)) AS rank "
            "FROM sentences s JOIN papers p ON p.paper_id = s.paper_id "
            "WHERE s.search_vector @@ websearch_to_tsquery('english', %s)"
        )
        params: list = [query, query]
        if corpus:
            sql += f" AND s.paper_id IN ({','.join(['%s'] * len(corpus))})"
            params.extend(corpus)
        sql += " ORDER BY rank DESC, s.sentence_id LIMIT %s"
        params.append(max(limit * 4, limit))
        rows = pg.execute(sql, params).fetchall()
        candidates = [{**dict(row), "retrieval": "pg_fts"} for row in rows]
    finally:
        pg.close()

    ranked = retrieval.rank_candidates(
        claim["claim_text"],
        claim.get("qualifiers") or {},
        candidates,
        direction=direction,
    )
    for candidate in ranked:
        candidate["direction"] = direction
        candidate["query"] = query
    return ranked[:limit]


def interrogate(
    claim_id: str,
    direction: str = "support",
    *,
    use_llm: bool = False,
    llm_client=None,
    retriever=None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    candidates = search_candidates(
        claim_id,
        direction=direction,
        limit=limit,
        retriever=retriever,
        llm_client=llm_client,
    )
    if use_llm:
        from services.claims import nli

        for candidate in candidates:
            result = nli.classify(
                (pg_read.get_claim(claim_id) or {}).get("claim_text", ""),
                candidate["quote"],
                llm_client,
            )
            candidate.update(
                {
                    "suggested_relation": result["relation"],
                    "confidence": result["confidence"],
                    "reason": result["reason"],
                }
            )
    else:
        for candidate in candidates:
            candidate.update(
                {
                    "suggested_relation": "underdetermines",
                    "confidence": 0.0,
                    "reason": "LLM classification disabled",
                }
            )
    return candidates
