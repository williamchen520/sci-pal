#!/usr/bin/env python3
"""Backfill Phase 0 tables from SQLite into PostgreSQL, idempotently."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

TABLES = (
    "projects",
    "project_members",
    "experiments",
    "experiment_revisions",
    "experiment_signatures",
    "experiment_audit",
    "experiment_access_requests",
    "experiment_runs",
)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def backfill(sqlite_path: Path, dsn: str, *, apply: bool) -> dict:
    import psycopg

    sqlite = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    sqlite.row_factory = sqlite3.Row
    report: dict = {"tables": {}, "apply": apply}
    try:
        with psycopg.connect(dsn) as pg:
            pg_columns = {
                table: {
                    row[0]
                    for row in pg.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=%s",
                        (table,),
                    )
                }
                for table in TABLES
            }
            for table in TABLES:
                exists = sqlite.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not exists:
                    report["tables"][table] = {"source": 0, "inserted": 0, "skipped": True}
                    continue
                rows = sqlite.execute(f"SELECT * FROM {_quote(table)}").fetchall()
                if not rows:
                    report["tables"][table] = {"source": 0, "inserted": 0}
                    continue
                columns = [
                    column
                    for column in rows[0].keys()
                    if column in pg_columns[table]
                ]
                if not columns:
                    report["tables"][table] = {
                        "source": len(rows),
                        "inserted": 0,
                        "error": "no common columns",
                    }
                    continue
                placeholders = ",".join("%s" for _ in columns)
                sql = (
                    f"INSERT INTO {_quote(table)} ({','.join(_quote(c) for c in columns)}) "
                    f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                )
                values = [tuple(row[column] for column in columns) for row in rows]
                inserted = 0
                if apply:
                    with pg.transaction():
                        for value in values:
                            inserted += pg.execute(sql, value).rowcount
                    if table == "experiment_audit":
                        pg.execute(
                            "SELECT setval(pg_get_serial_sequence('experiment_audit','id'), "
                            "COALESCE((SELECT max(id) FROM experiment_audit), 1))"
                        )
                        pg.commit()
                report["tables"][table] = {
                    "source": len(rows),
                    "inserted": inserted,
                    "columns": columns,
                }
    finally:
        sqlite.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sqlite", default="G:/sciPal_deploy/data/research.db")
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = backfill(Path(args.sqlite), args.pg_dsn, apply=args.apply)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
