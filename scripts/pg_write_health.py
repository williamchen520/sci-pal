#!/usr/bin/env python3
"""Report dual-write health: SQLite outbox and optional PG row-count diff."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLES = (
    "papers", "sections", "paragraphs", "sentences", "figures", "tables",
    "citations", "sentence_links", "paper_links", "claim_cards",
    "claim_card_evidence", "claim_card_events", "watch_items",
    "watch_profiles", "watch_runs", "watch_seen", "users", "workspaces",
    "memberships", "review_projects", "review_events",
)


def sqlite_health(db: Path) -> dict:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        has_outbox = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dual_write_outbox'"
        ).fetchone()
        if not has_outbox:
            return {"outbox": False}
        pending = conn.execute(
            "SELECT count(*) FROM dual_write_outbox WHERE processed_at IS NULL"
        ).fetchone()[0]
        oldest = conn.execute(
            "SELECT min(created_at) FROM dual_write_outbox WHERE processed_at IS NULL"
        ).fetchone()[0]
        failures = conn.execute(
            "SELECT count(*) FROM dual_write_outbox WHERE attempts > 0 AND processed_at IS NULL"
        ).fetchone()[0]
        by_table = conn.execute(
            "SELECT table_name, count(*) FROM dual_write_outbox "
            "WHERE processed_at IS NULL GROUP BY table_name ORDER BY count(*) DESC"
        ).fetchall()
        counts = {}
        for table in TABLES:
            try:
                counts[table] = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            except sqlite3.DatabaseError:
                counts[table] = None
        return {
            "outbox": True,
            "pending": pending,
            "oldest_pending": oldest,
            "failed_pending": failures,
            "pending_by_table": by_table,
            "sqlite_counts": counts,
        }
    finally:
        conn.close()


def pg_counts(dsn: str) -> dict:
    import psycopg
    from psycopg.rows import dict_row

    counts = {}
    with psycopg.connect(dsn, row_factory=dict_row) as pg:
        for table in TABLES:
            try:
                counts[table] = pg.execute(f'SELECT count(*) AS n FROM "{table}"').fetchone()["n"]
            except Exception:  # noqa: BLE001
                counts[table] = None
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "research.db"))
    parser.add_argument("--pg-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    args = parser.parse_args()

    report = {"sqlite": sqlite_health(Path(args.db))}
    if args.pg_dsn:
        try:
            pg = pg_counts(args.pg_dsn)
            report["pg_counts"] = pg
            sqlite_counts = report["sqlite"].get("sqlite_counts", {})
            report["diff"] = {
                table: (sqlite_counts.get(table), pg.get(table))
                for table in TABLES
                if sqlite_counts.get(table) != pg.get(table)
            }
        except Exception as exc:  # noqa: BLE001
            report["pg_error"] = str(exc)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
