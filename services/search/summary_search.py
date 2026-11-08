"""Keyword retrieval over section summaries (RAPTOR-lite channel)."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was",
    "were", "has", "have", "what", "how", "does",
}


class SummarySearch:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = str(db_path)

    def search(self, query: str, top_k: int = 3, paper_id: str = "") -> List[Dict]:
        terms = [
            token
            for token in re.findall(r"[A-Za-z0-9]+", query)
            if len(token) > 2 and token.lower() not in STOP
        ][:8]
        if not terms:
            return []
        match = " OR ".join(f'"{term}"' for term in terms)
        if os.environ.get("SCIPAL_SEARCH_META_BACKEND", "").strip().lower() in {
            "postgres", "postgresql", "pg", "1", "true"
        }:
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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT s.summary_id, s.paper_id, s.section_id, s.level, s.title, "
                "s.text, bm25(summaries_fts) AS rank "
                "FROM summaries_fts JOIN summaries s ON s.summary_id = summaries_fts.summary_id "
                "WHERE summaries_fts MATCH ? "
                + ("AND s.paper_id = ? " if paper_id else "")
                + "ORDER BY rank LIMIT ?",
                (match, paper_id, top_k) if paper_id else (match, top_k),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
