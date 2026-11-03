#!/usr/bin/env python3
"""Repair missing SQLite FTS rows before FTS single-stack work.

Dry-run by default. --apply inserts missing paragraphs/summaries rows and
installs summaries FTS triggers. Paragraph triggers already exist.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def _counts(conn: sqlite3.Connection) -> dict:
    return {
        "paragraphs": conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0],
        "paragraphs_fts": conn.execute("SELECT COUNT(*) FROM paragraphs_fts").fetchone()[0],
        "summaries": conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0],
        "summaries_fts": conn.execute("SELECT COUNT(*) FROM summaries_fts").fetchone()[0],
    }


def _missing_rows(conn: sqlite3.Connection) -> tuple[list[tuple], list[tuple]]:
    """Return missing paragraph/summary rows using ID sets (FTS scans are slow)."""
    para_ids = {row[0] for row in conn.execute("SELECT para_id FROM paragraphs_fts")}
    paragraphs = [
        row
        for row in conn.execute(
            "SELECT para_id, paper_id, section_level1, section_level2, text FROM paragraphs"
        )
        if row[0] not in para_ids
    ]
    summary_ids = {row[0] for row in conn.execute("SELECT summary_id FROM summaries_fts")}
    summaries = [
        row
        for row in conn.execute(
            "SELECT summary_id, paper_id, section_id, title, text FROM summaries"
        )
        if row[0] not in summary_ids
    ]
    return paragraphs, summaries


def _missing(conn: sqlite3.Connection) -> dict:
    paragraphs, summaries = _missing_rows(conn)
    return {"paragraphs": len(paragraphs), "summaries": len(summaries)}


def repair(db_path: str | Path, *, apply: bool = False) -> dict:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        before = _counts(conn)
        missing_paragraphs, missing_summaries = _missing_rows(conn)
        missing = {"paragraphs": len(missing_paragraphs), "summaries": len(missing_summaries)}
        if apply:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executemany(
                    "INSERT INTO paragraphs_fts (para_id, paper_id, section_l1, section_l2, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    missing_paragraphs,
                )
                conn.executemany(
                    "INSERT INTO summaries_fts (summary_id, paper_id, section_id, title, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    missing_summaries,
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS summaries_ai AFTER INSERT ON summaries BEGIN "
                    "INSERT INTO summaries_fts (summary_id, paper_id, section_id, title, text) "
                    "VALUES (new.summary_id, new.paper_id, new.section_id, new.title, new.text); END"
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS summaries_ad AFTER DELETE ON summaries BEGIN "
                    "DELETE FROM summaries_fts WHERE summary_id = old.summary_id; END"
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS summaries_au AFTER UPDATE ON summaries BEGIN "
                    "DELETE FROM summaries_fts WHERE summary_id = old.summary_id; "
                    "INSERT INTO summaries_fts (summary_id, paper_id, section_id, title, text) "
                    "VALUES (new.summary_id, new.paper_id, new.section_id, new.title, new.text); END"
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "db": str(db_path),
            "applied": apply,
            "before": before,
            "missing_before": missing,
            "after": _counts(conn),
            "missing_after": _missing(conn),
            "summaries_triggers": [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('summaries_ai','summaries_ad','summaries_au') ORDER BY name"
                )
            ],
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = repair(args.db, apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    missing = result["missing_after"]
    return 0 if not args.apply or (missing["paragraphs"] == 0 and missing["summaries"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
