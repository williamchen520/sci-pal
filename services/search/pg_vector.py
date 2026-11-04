"""pgvector paragraph search adapter (G2).

The existing Chroma path stays untouched until the shadow comparison passes.
"""

from __future__ import annotations

import os
from typing import List, Optional

from services.search.pg_fts import ParagraphHit


def vector_literal(values) -> str:
    return "[" + ",".join(f"{float(value):.6f}" for value in values) + "]"


class PGVectorParagraphSearch:
    def __init__(self, dsn: Optional[str] = None, *, connector=None):
        self.dsn = dsn or os.environ.get("SCIPAL_PARADEDB_DSN") or os.environ.get(
            "SCIPAL_PG_DSN", ""
        )
        self._connector = connector

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        from services.db.pg_pool import pg_connection

        return pg_connection(self.dsn), True

    def search(
        self,
        query_embedding: List[float],
        *,
        top_k: int = 10,
        paper_id: str = "",
    ) -> List[ParagraphHit]:
        if not query_embedding:
            return []
        literal = vector_literal(query_embedding)
        where = "TRUE"
        params: list = [literal]
        if paper_id:
            where += " AND e.paper_id = %s"
            params.append(paper_id)
        params.extend([literal, top_k])
        sql = f"""
            SELECT e.para_id, e.paper_id, p.section_level1, p.section_level2,
                   p.text, 1 - (e.embedding <=> %s::vector) AS rank
            FROM paragraph_embeddings e
            JOIN paragraphs p ON p.para_id = e.para_id
            WHERE {where}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [ParagraphHit(**row) for row in rows]
