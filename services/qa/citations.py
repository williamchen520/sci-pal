"""Paragraph-level citation metadata for QA sources."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def paragraph_citation(
    para_id: str, db_path: Path | str = DEFAULT_DB
) -> Dict[str, object]:
    if not para_id:
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT sentence_id FROM sentences WHERE para_id = ? ORDER BY sequence",
            (para_id,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "paragraph_id": para_id,
        "sentence_ids": [row[0] for row in rows],
    }
