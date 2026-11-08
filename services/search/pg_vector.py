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
        self.dsn = dsn
        self._connector = connector

    def _connection(self):
        if self._connector is not None:
            return self._connector(), False
        from services.db.pg_pool import main_read_connection, pg_connection

        return (pg_connection(self.dsn) if self.dsn else main_read_connection()), True

    def search(
        self,
        query_embedding: List[float],
        *,
        top_k: int = 10,
        paper_id: str = "",
    ) -> List[ParagraphHit]:
        if query_embedding is None or len(query_embedding) == 0:
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
            JOIN papers pp ON pp.paper_id = e.paper_id AND pp.duplicate_of IS NULL
            WHERE {where}
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
        """
        pg, close = self._connection()
        try:
            if self._connector is None:
                try:
                    ef_search = max(
                        1, min(1000, int(os.environ.get("SCIPAL_PGVECTOR_EF_SEARCH", "200")))
                    )
                except ValueError:
                    ef_search = 100
                pg.execute(f"SET hnsw.ef_search = {ef_search}")
            rows = pg.execute(sql, params).fetchall()
        finally:
            if close:
                pg.close()
        return [ParagraphHit(**row) for row in rows]
