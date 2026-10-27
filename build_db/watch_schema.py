"""Watch schema: profiles, journal catalog, runs, items, seen keys."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_catalog (
    issn_l TEXT PRIMARY KEY,
    name TEXT,
    openalex_source_id TEXT,
    sjr REAL,
    sjr_quartile TEXT,
    metric_year INTEGER,
    works_count INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS watch_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    field_text TEXT,
    keywords TEXT,
    openalex_topic_ids TEXT,
    interval_days INTEGER DEFAULT 3,
    window_days INTEGER DEFAULT 7,
    top_journal_count INTEGER DEFAULT 30,
    max_items INTEGER DEFAULT 3,
    same_journal_limit INTEGER DEFAULT 2,
    metric_type TEXT DEFAULT 'openalex',
    metric_min REAL,
    language TEXT DEFAULT 'zh',
    delivery TEXT DEFAULT 'dsh',
    enabled INTEGER DEFAULT 1,
    last_run_at TEXT,
    next_run_at TEXT,
    last_push_at TEXT,
    last_heartbeat_at TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS watch_profile_journals (
    profile_id INTEGER,
    issn_l TEXT,
    name TEXT,
    source TEXT,
    added_at TEXT,
    PRIMARY KEY (profile_id, issn_l)
);

CREATE TABLE IF NOT EXISTS watch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER,
    window_start TEXT,
    window_end TEXT,
    status TEXT,
    found INTEGER DEFAULT 0,
    selected INTEGER DEFAULT 0,
    imported_full INTEGER DEFAULT 0,
    imported_abstract INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    digest_md TEXT,
    error TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS watch_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    profile_id INTEGER,
    paper_id TEXT,
    doi TEXT,
    title TEXT,
    journal TEXT,
    published TEXT,
    score REAL,
    reason TEXT,
    acquisition TEXT,
    status TEXT DEFAULT 'new',
    read_at TEXT
);

CREATE TABLE IF NOT EXISTS watch_seen (
    profile_id INTEGER,
    dedup_key TEXT,
    paper_id TEXT,
    first_seen_at TEXT,
    status TEXT DEFAULT 'new',
    read_at TEXT,
    PRIMARY KEY (profile_id, dedup_key)
);

CREATE INDEX IF NOT EXISTS idx_watch_items_run ON watch_items(run_id);
CREATE INDEX IF NOT EXISTS idx_watch_items_profile ON watch_items(profile_id, status);
CREATE INDEX IF NOT EXISTS idx_watch_runs_profile ON watch_runs(profile_id, id);
"""


def migrate(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA busy_timeout=60000")
    try:
        conn.executescript(SCHEMA)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(papers)")}
        if "acquisition" not in cols:
            conn.execute("ALTER TABLE papers ADD COLUMN acquisition TEXT DEFAULT 'fulltext'")
        conn.commit()
    finally:
        conn.close()
    return {"ok": 1}


if __name__ == "__main__":
    print(migrate())
