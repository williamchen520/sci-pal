"""Claim–evidence schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    paper_id TEXT,
    sentence_id TEXT,
    claim_text TEXT,
    claim_type TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS claim_evidence (
    claim_id TEXT,
    evidence_sentence_id TEXT,
    relation TEXT,
    confidence REAL,
    PRIMARY KEY (claim_id, evidence_sentence_id)
);
CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id);
CREATE INDEX IF NOT EXISTS idx_papers_doi_lower ON papers(lower(doi));
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
