"""Trust flags schema (retractions / corrections)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_flags (
    paper_id TEXT NOT NULL,
    flag_type TEXT NOT NULL,
    source TEXT NOT NULL,
    detail TEXT,
    checked_at TEXT,
    PRIMARY KEY (paper_id, flag_type, source)
);
CREATE INDEX IF NOT EXISTS idx_paper_flags_paper ON paper_flags(paper_id);
"""


def migrate(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return {"ok": 1}


if __name__ == "__main__":
    print(migrate())
