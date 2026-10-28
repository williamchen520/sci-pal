"""Add and backfill citation intent on sentence_links."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

from services.search.citation_intent import classify

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def migrate(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=60000")
    stats = {"added": 0, "updated": 0}
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sentence_links)")}
        if "intent" not in cols:
            conn.execute("ALTER TABLE sentence_links ADD COLUMN intent TEXT")
            stats["added"] = 1
        rows = conn.execute(
            "SELECT sl.link_id, s.text FROM sentence_links sl "
            "JOIN sentences s ON s.sentence_id = sl.sentence_id "
            "WHERE sl.target_type = 'citation' AND (sl.intent IS NULL OR sl.intent = '')"
        ).fetchall()
        updates = [(classify(text or ""), link_id) for link_id, text in rows]
        conn.executemany("UPDATE sentence_links SET intent = ? WHERE link_id = ?", updates)
        stats["updated"] = len(updates)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sentence_links_intent "
            "ON sentence_links(target_type, intent)"
        )
        conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    print(migrate())
