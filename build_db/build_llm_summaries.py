"""Generate LLM summaries for a subset of sections.

Usage:
    python -m build_db.build_llm_summaries --limit 100 --model qwen2.5:3b
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict

from services.search.summary_llm import summarize

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def ensure_column(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(summaries)")}
    if "summary_source" not in cols:
        conn.execute(
            "ALTER TABLE summaries ADD COLUMN summary_source TEXT DEFAULT 'extractive'"
        )
        conn.commit()


def build(db_path: Path | str = DEFAULT_DB, limit: int = 100, model: str = "qwen2.5:3b") -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    stats = {"updated": 0, "skipped": 0}
    try:
        ensure_column(conn)
        rows = conn.execute(
            "SELECT summary_id, title, text FROM summaries "
            "WHERE COALESCE(summary_source, 'extractive') != 'llm' "
            "ORDER BY length(text) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for summary_id, title, text in rows:
            generated = summarize(title or "", text or "", model=model)
            if not generated:
                stats["skipped"] += 1
                continue
            conn.execute(
                "UPDATE summaries SET text = ?, token_count = ?, summary_source = 'llm' "
                "WHERE summary_id = ?",
                (generated, len(generated.split()), summary_id),
            )
            stats["updated"] += 1
            if stats["updated"] % 10 == 0:
                conn.commit()
        conn.commit()
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--model", default="qwen2.5:3b")
    args = parser.parse_args()
    print(build(args.db, args.limit, args.model))
