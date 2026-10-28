"""Systematic review schema: projects, screening, evidence rows."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS review_projects (
    project_id TEXT PRIMARY KEY,
    owner TEXT DEFAULT 'default',
    name TEXT,
    field_text TEXT,
    pico_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS review_project_members (
    project_id TEXT,
    member TEXT,
    role TEXT DEFAULT 'reviewer',
    added_at TEXT,
    PRIMARY KEY (project_id, member)
);
CREATE TABLE IF NOT EXISTS review_project_papers (
    project_id TEXT,
    paper_id TEXT,
    added_at TEXT,
    PRIMARY KEY (project_id, paper_id)
);
CREATE TABLE IF NOT EXISTS screening_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    paper_id TEXT,
    stage TEXT,
    decision TEXT,
    reason TEXT,
    reviewer TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS evidence_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    paper_id TEXT,
    design TEXT,
    sample_size TEXT,
    intervention TEXT,
    comparator TEXT,
    outcomes TEXT,
    effect TEXT,
    source_sentence TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS adjudications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    paper_id TEXT,
    decision TEXT,
    reason TEXT,
    editor TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_screening_project ON screening_decisions(project_id, paper_id);
CREATE INDEX IF NOT EXISTS idx_adjudications_project ON adjudications(project_id, paper_id);
CREATE TABLE IF NOT EXISTS review_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    actor TEXT,
    action TEXT,
    target TEXT,
    detail TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_events_project ON review_events(project_id, id);
CREATE TABLE IF NOT EXISTS risk_of_bias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    paper_id TEXT,
    domain TEXT,
    judgement TEXT,
    support TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence_rows(project_id);
CREATE INDEX IF NOT EXISTS idx_rob_project ON risk_of_bias(project_id, paper_id);
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
