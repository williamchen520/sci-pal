"""Section/paper summaries (RAPTOR-lite, extractive).

This is the first step of the RAPTOR workstream: build a summary layer that can
be retrieved independently of paragraphs. Summaries are extractive (no LLM) so
they are cheap and reproducible; embeddings can be added later.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Dict, List

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS summaries (
    summary_id TEXT PRIMARY KEY,
    paper_id TEXT,
    section_id TEXT,
    level INTEGER,
    title TEXT,
    text TEXT,
    token_count INTEGER,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_summaries_paper ON summaries(paper_id);
CREATE VIRTUAL TABLE IF NOT EXISTS summaries_fts USING fts5(
    summary_id, paper_id, section_id, title, text
);
"""


def _first_sentence(text: str, limit: int = 240) -> str:
    for end in (". ", "。", "! ", "? "):
        index = text.find(end)
        if 0 < index < limit:
            return text[: index + 1].strip()
    return text[:limit].strip()


def summarize_section(title: str, paragraphs: List[str]) -> str:
    paragraphs = [p.strip() for p in paragraphs if p and p.strip()]
    if not paragraphs:
        return title
    head = _first_sentence(paragraphs[0])
    tail = _first_sentence(paragraphs[-1]) if len(paragraphs) > 1 else ""
    parts = [title] if title else []
    parts.append(head)
    if tail and tail != head:
        parts.append(tail)
    return " ".join(part for part in parts if part)[:600]


def build(db_path: Path | str = DEFAULT_DB, limit: int = 0) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    stats = {"sections": 0, "papers": 0}
    try:
        query = (
            "SELECT s.section_id, s.paper_id, s.title, "
            "GROUP_CONCAT(p.text, '|||') AS body "
            "FROM sections s JOIN paragraphs p ON p.section_id = s.section_id "
            "GROUP BY s.section_id ORDER BY s.paper_id, s.seq"
        )
        if limit:
            query += f" LIMIT {int(limit)}"
        for section_id, paper_id, title, body in conn.execute(query):
            paragraphs = body.split("|||") if body else []
            text = summarize_section(title or "", paragraphs)
            summary_id = f"sum_{section_id}"
            conn.execute(
                "INSERT OR REPLACE INTO summaries "
                "(summary_id, paper_id, section_id, level, title, text, token_count, created_at) "
                "VALUES (?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)",
                (summary_id, paper_id, section_id, title, text, len(text.split())),
            )
            stats["sections"] += 1
        conn.execute("DELETE FROM summaries_fts")
        conn.execute(
            "INSERT INTO summaries_fts (summary_id, paper_id, section_id, title, text) "
            "SELECT summary_id, paper_id, section_id, title, text FROM summaries"
        )
        conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB))
