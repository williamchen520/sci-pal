"""Keyword retrieval over section summaries (RAPTOR-lite channel)."""

from __future__ import annotations

import os
import re
from typing import Dict, List

STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was",
    "were", "has", "have", "what", "how", "does",
}


class SummarySearch:
    def __init__(self, db_path=None) -> None:
        # db_path is kept for call-site compatibility; storage is PostgreSQL.
        self.db_path = db_path

    def search(self, query: str, top_k: int = 3, paper_id: str = "") -> List[Dict]:
        terms = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", query)
            if len(token) > 2 and token.lower() not in STOP
        ][:8]
        if not terms:
            return []
        from services.db.pg_pool import main_read_connection

        ts_query = " | ".join(terms)
        pg = main_read_connection()
        try:
            rows = pg.execute(
                "SELECT summary_id, paper_id, section_id, level, title, text, "
                "ts_rank(to_tsvector('english', coalesce(title,'') || ' ' || coalesce(text,'')), "
                "to_tsquery('english', %s)) AS rank "
                "FROM summaries "
                "WHERE to_tsvector('english', coalesce(title,'') || ' ' || coalesce(text,'')) "
                "@@ to_tsquery('english', %s) "
                "AND paper_id IN (SELECT paper_id FROM papers WHERE duplicate_of IS NULL) "
                + ("AND paper_id = %s " if paper_id else "")
                + "ORDER BY rank DESC LIMIT %s",
                (ts_query, ts_query, paper_id, top_k) if paper_id else (ts_query, ts_query, top_k),
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []
        finally:
            pg.close()
