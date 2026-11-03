#!/usr/bin/env python3
"""Repair abstract corpus FTS coverage and install keep-in-sync triggers."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def repair(db_path: str | Path, *, apply: bool = False) -> dict:
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        indexed = {row[0] for row in conn.execute("SELECT pmid FROM papers_fts")}
        missing = [
            row
            for row in conn.execute(
                "SELECT pmid, title, abstract, authors, journal, topic FROM papers"
            )
            if row[0] not in indexed
        ]
        before = {
            "papers": conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
            "papers_fts": conn.execute("SELECT COUNT(*) FROM papers_fts").fetchone()[0],
        }
        if apply:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.executemany(
                    "INSERT INTO papers_fts (pmid, title, abstract, authors, journal, topic) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    missing,
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN "
                    "INSERT INTO papers_fts (pmid, title, abstract, authors, journal, topic) "
                    "VALUES (new.pmid, new.title, new.abstract, new.authors, new.journal, new.topic); END"
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN "
                    "DELETE FROM papers_fts WHERE pmid = old.pmid; END"
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN "
                    "DELETE FROM papers_fts WHERE pmid = old.pmid; "
                    "INSERT INTO papers_fts (pmid, title, abstract, authors, journal, topic) "
                    "VALUES (new.pmid, new.title, new.abstract, new.authors, new.journal, new.topic); END"
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "db": str(db_path),
            "applied": apply,
            "missing_before": len(missing),
            "before": before,
            "after": {
                "papers": conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0],
                "papers_fts": conn.execute("SELECT COUNT(*) FROM papers_fts").fetchone()[0],
            },
            "triggers": [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' "
                    "AND name IN ('papers_ai','papers_ad','papers_au') ORDER BY name"
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
    return 0 if not args.apply or result["after"]["papers"] == result["after"]["papers_fts"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
