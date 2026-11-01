"""Source-aware sentence-level FTS for scipal_v2.

One query, two source contracts:
- XML: source_nodes.source_path (XPath), page/bbox NULL
- PDF: page + bbox; source_path points at the PDF paragraph node
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional

from services.search.fts_query_builder import _extract_keywords


@dataclass
class SentenceHit:
    sentence_id: str
    paper_id: str
    para_id: str
    section_id: Optional[str]
    text: str
    source_type: str
    page: Optional[int]
    bbox: Optional[str]
    source_path: Optional[str]
    title: Optional[str]
    rank: float

    def as_dict(self) -> dict:
        return asdict(self)


class SentenceFTS:
    def __init__(self, dsn: Optional[str] = None, *, connector=None):
        self.dsn = dsn or os.environ.get("SCIPAL_PG_V2_DSN", "")
        self._connector = connector

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(self.dsn, row_factory=dict_row), True

    def search(
        self,
        query: str,
        *,
        top_k: int = 20,
        source_type: Optional[str] = None,
        match: str = "any",
        term_limit: int = 12,
        ranker: str = "rank",
    ) -> List[SentenceHit]:
        query = (query or "").strip()
        if not query:
            return []
        if match not in ("any", "all"):
            raise ValueError("match must be any or all")
        if source_type not in (None, "xml", "pdf"):
            raise ValueError("source_type must be xml, pdf or None")
        terms = _extract_keywords(query)
        if not terms:
            return []
        if ranker not in ("rank", "rank_cd"):
            raise ValueError("ranker must be rank or rank_cd")
        operator = " | " if match == "any" else " & "
        rank_expr = "ts_rank_cd" if ranker == "rank_cd" else "ts_rank"
        ts_query = operator.join(terms[: max(1, min(term_limit, 12))])
        where = "s.search_vector @@ q.query"
        params: list = [ts_query]
        if source_type:
            where += " AND s.source_type = %s"
            params.append(source_type)
        params.append(top_k)
        sql = f"""
            WITH q AS (SELECT to_tsquery('english', %s) AS query)
            SELECT s.sentence_id, s.paper_id, s.para_id, s.section_id,
                   s.text, s.source_type, s.page, s.bbox,
                   sn.source_path, p.title,
                   {rank_expr}(s.search_vector, q.query) AS rank
            FROM sentences s
            JOIN papers p ON p.paper_id = s.paper_id
            LEFT JOIN source_nodes sn ON sn.node_id = s.source_node_id
            CROSS JOIN q
            WHERE {where}
            ORDER BY rank DESC, s.sentence_id
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [SentenceHit(**row) for row in rows]

    def recall(
        self,
        query: str,
        *,
        top_k: int = 200,
        source_type: Optional[str] = None,
    ) -> List[SentenceHit]:
        """Cheap GIN recall without database-side ranking."""
        query = (query or "").strip()
        if not query:
            return []
        if source_type not in (None, "xml", "pdf"):
            raise ValueError("source_type must be xml, pdf or None")
        terms = _extract_keywords(query)
        if not terms:
            return []
        ts_query = " | ".join(terms[:12])
        where = "s.search_vector @@ q.query"
        params: list = [ts_query]
        if source_type:
            where += " AND s.source_type = %s"
            params.append(source_type)
        params.append(top_k)
        sql = f"""
            WITH q AS (SELECT to_tsquery('english', %s) AS query)
            SELECT s.sentence_id, s.paper_id, s.para_id, s.section_id,
                   s.text, s.source_type, s.page, s.bbox,
                   sn.source_path, p.title, 0.0::float8 AS rank
            FROM sentences s
            JOIN papers p ON p.paper_id = s.paper_id
            LEFT JOIN source_nodes sn ON sn.node_id = s.source_node_id
            CROSS JOIN q
            WHERE {where}
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [SentenceHit(**row) for row in rows]

    def aggregate_by_paragraph(self, hits: Iterable[SentenceHit]) -> List[dict]:
        best: dict[str, dict] = {}
        for hit in hits:
            current = best.get(hit.para_id)
            if current is None:
                best[hit.para_id] = {
                    "para_id": hit.para_id,
                    "paper_id": hit.paper_id,
                    "section_id": hit.section_id,
                    "source_type": hit.source_type,
                    "page": hit.page,
                    "bbox": hit.bbox,
                    "text": hit.text,
                    "rank": hit.rank,
                    "sentence_ids": [hit.sentence_id],
                }
            elif hit.rank > current["rank"]:
                current.update(
                    {
                        "text": hit.text,
                        "rank": hit.rank,
                        "page": hit.page,
                        "bbox": hit.bbox,
                        "source_type": hit.source_type,
                    }
                )
                current["sentence_ids"].append(hit.sentence_id)
            else:
                current["sentence_ids"].append(hit.sentence_id)
        return sorted(best.values(), key=lambda item: item["rank"], reverse=True)
