"""Claim pilot schema: claim cards, evidence anchors, events."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS claim_cards (
    claim_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'ws_default',
    title TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL DEFAULT 'empirical',
    status TEXT NOT NULL DEFAULT 'draft',
    confidence REAL NOT NULL DEFAULT 0.0,
    qualifiers_json TEXT NOT NULL DEFAULT '{}',
    warrant TEXT,
    backing TEXT,
    rebuttal TEXT,
    strongest_counter TEXT,
    decision TEXT NOT NULL DEFAULT 'pending',
    decision_note TEXT,
    decided_by TEXT,
    decided_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claim_card_evidence (
    evidence_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    node_type TEXT NOT NULL DEFAULT 'sentence',
    node_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    strength REAL NOT NULL DEFAULT 0.0,
    quote TEXT NOT NULL,
    rationale TEXT,
    source_type TEXT NOT NULL DEFAULT 'literature',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(claim_id, node_id, relation)
);

CREATE TABLE IF NOT EXISTS claim_card_events (
    event_id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_claim_cards_status ON claim_cards(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_card_evidence(claim_id, relation);
CREATE INDEX IF NOT EXISTS idx_claim_events_claim ON claim_card_events(claim_id, created_at);
"""


def migrate(db_path: Path | str = DEFAULT_DB) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return {"ok": 1}


if __name__ == "__main__":
    print(migrate())
