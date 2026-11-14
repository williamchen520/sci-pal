"""Sentence-level evidence retrieval inside one paper."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection

MAX_TOP_K = 20


def paper_evidence(paper_id: str, query: str, *, top_k: int = 8) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    top_k = max(1, min(int(top_k), MAX_TOP_K))
    pg = corpus_connection()
    try:
        rows = pg.execute(
            """
            WITH q AS (SELECT websearch_to_tsquery('english', %s) AS query)
            SELECT s.sentence_id, s.para_id, s.paper_id, s.text, s.sequence,
                   s.page, s.bbox, s.char_start, s.char_end,
                   p.section_level1, p.section_level2, p.section_path,
                   ts_rank_cd(s.search_vector, q.query) AS score
            FROM sentences s
            JOIN paragraphs p ON p.para_id = s.para_id
            CROSS JOIN q
            WHERE s.paper_id = %s AND s.search_vector @@ q.query
            ORDER BY score DESC, s.sentence_id
            LIMIT %s
            """,
            (query, paper_id, top_k),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
