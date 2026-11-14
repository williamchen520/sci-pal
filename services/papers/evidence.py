"""Sentence evidence retrieval: paragraph vector recall + sentence FTS."""

from __future__ import annotations

import logging
import os
from typing import Any

from services.db.pg_pool import corpus_connection
from services.search.pg_vector import PGVectorParagraphSearch

LOGGER = logging.getLogger(__name__)
MAX_TOP_K = 20
_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        model_path = os.environ.get("SCIPAL_EMBEDDING_MODEL", "").strip() or "BAAI/bge-base-en-v1.5"
        device = os.environ.get("SCIPAL_PAPER_EMBEDDING_DEVICE", "cpu").strip() or "cpu"
        _MODEL = SentenceTransformer(model_path, device=device)
    return _MODEL


def _vector_candidates(paper_id: str, query: str, top_k: int) -> list[dict[str, Any]]:
    embedding = _model().encode([query], normalize_embeddings=True)[0]
    hits = PGVectorParagraphSearch().search(embedding.tolist(), top_k=top_k, paper_id=paper_id)
    return [
        {
            "para_id": hit.para_id,
            "score": float(hit.rank),
            "section_level1": hit.section_level1,
            "section_level2": hit.section_level2,
        }
        for hit in hits
    ]


def _sentence_fts(
    paper_id: str, query: str, para_ids: list[str], top_k: int
) -> list[dict[str, Any]]:
    where = (
        "s.paper_id = %s AND s.search_vector @@ q.query "
        "AND p.section_level1 NOT IN ('figure_caption','table_caption') "
        "AND p.text !~* '^(Fig\\.?|Figure|Table)\\s+[0-9]+\\s*\\|'"
    )
    base_params: list[Any] = [paper_id]
    if para_ids:
        where += " AND s.para_id = ANY(%s)"
        base_params.append(para_ids)
    pg = corpus_connection()
    try:
        def run(ts_query: str) -> list[dict[str, Any]]:
            rows = pg.execute(
                f"""
                WITH q AS (SELECT websearch_to_tsquery('english', %s) AS query)
                SELECT s.sentence_id, s.para_id, s.paper_id, s.text, s.sequence,
                       s.page, s.bbox, s.char_start, s.char_end,
                       p.section_level1, p.section_level2, p.section_path,
                       ts_rank_cd(s.search_vector, q.query) AS score
                FROM sentences s
                JOIN paragraphs p ON p.para_id = s.para_id
                CROSS JOIN q
                WHERE {where}
                ORDER BY score DESC, s.sentence_id
                LIMIT %s
                """,
                (ts_query, *base_params, top_k),
            ).fetchall()
            return [dict(row) for row in rows]

        rows = run(query)
        if not rows and " " in query:
            rows = run(" or ".join(part for part in query.split() if part))
        return rows
    finally:
        pg.close()


def paper_evidence(paper_id: str, query: str, *, top_k: int = 8) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    top_k = max(1, min(int(top_k), MAX_TOP_K))
    para_ids: list[str] = []
    try:
        candidates = _vector_candidates(paper_id, query, max(top_k * 4, 20))
        para_ids = [row["para_id"] for row in candidates]
    except Exception as exc:  # model/index unavailable must not break FTS
        LOGGER.warning("paper vector recall unavailable: %s", exc)
    rows = _sentence_fts(paper_id, query, para_ids, top_k)
    for row in rows:
        row["match_type"] = "paragraph_vector+sentence_fts" if para_ids else "sentence_fts"
    return rows
