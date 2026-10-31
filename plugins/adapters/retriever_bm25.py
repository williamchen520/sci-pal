"""Adapter B1: SQLite FTS5/BM25 only."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.plugins.retriever_contracts import RetrieverAdapter, RetrieverCandidate
from services.search.fts_query_builder import FTSQueryBuilder

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "research.db"


class BM25Retriever(RetrieverAdapter):
    name = "retriever-bm25"
    version = "0.1.0"

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(os.environ.get("SCIPAL_DB") or db_path or DEFAULT_DB)
        self.builder = FTSQueryBuilder()

    def retrieve(
        self,
        query: str,
        *,
        corpus: List[str],
        top_k: int = 10,
        options: Optional[Dict[str, Any]] = None,
    ) -> List[RetrieverCandidate]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fts_query = self.builder.build(query)
            marks = ",".join("?" * len(corpus))
            rows = conn.execute(
                f"""
                SELECT para_id, paper_id, text, bm25(paragraphs_fts) AS score
                FROM paragraphs_fts
                WHERE paragraphs_fts MATCH ? AND paper_id IN ({marks})
                ORDER BY score
                LIMIT ?
                """,
                [fts_query, *corpus, int(top_k)],
            ).fetchall()
        finally:
            conn.close()
        return [
            RetrieverCandidate(
                paper_id=str(row["paper_id"]),
                node_id=str(row["para_id"]),
                text=str(row["text"] or ""),
                score=-float(row["score"] or 0.0),
                rank=index + 1,
            )
            for index, row in enumerate(rows)
        ]
