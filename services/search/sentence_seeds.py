"""Sentence-level FTS seeding for paragraph candidates."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Dict, List

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was",
    "were", "has", "have", "what", "how", "does", "did", "into", "than",
}


class SentenceSeedSearch:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = str(db_path)

    def search(self, query: str, top_k: int = 50) -> List[Dict]:
        terms = [
            token
            for token in TOKEN_RE.findall(query or "")
            if len(token) > 1 and token.lower() not in STOP
        ][:10]
        if not terms:
            return []
        match = " OR ".join(f'"{term}"' for term in terms)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT s.para_id, bm25(sentences_fts) AS rank "
                "FROM sentences_fts f "
                "JOIN sentences s ON s.sentence_id = f.sentence_id "
                "WHERE sentences_fts MATCH ? "
                "ORDER BY rank LIMIT ?",
                (match, top_k * 5),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        best = {}
        for row in rows:
            para_id = row["para_id"]
            if not para_id:
                continue
            rank = float(row["rank"] or 0.0)
            if para_id not in best or rank < best[para_id]:
                best[para_id] = rank
        ordered = sorted(best.items(), key=lambda item: item[1])[:top_k]
        return [
            {
                "para_id": para_id,
                "rank": index + 1,
                "score": round(1.0 / (1.0 + abs(rank)), 6),
            }
            for index, (para_id, rank) in enumerate(ordered)
        ]
