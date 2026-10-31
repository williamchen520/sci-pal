#!/usr/bin/env python3
"""P4 staging soak: write metadata into a staging SQLite copy, replay to a
staging PostgreSQL database, and compare counts.

This never touches the production SQLite database or the production PG schema.
The staging database name must end with ``_soak``.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.db.dual_write import DEFAULT_TABLES, install, replay  # noqa: E402
from services.db.etl import PostgresCopyWriter, quote_ident, run_etl  # noqa: E402


def _require_soak_name(name: str) -> str:
    if not name.endswith("_soak"):
        raise SystemExit(f"staging database must end with _soak, got {name!r}")
    return name


def create_staging_db(admin_dsn: str, dbname: str, recreate: bool) -> str:
    from psycopg import conninfo

    dbname = _require_soak_name(dbname)
    params = conninfo.conninfo_to_dict(admin_dsn)
    params["dbname"] = "postgres"
    admin = conninfo.make_conninfo(**params)
    with __import__("psycopg").connect(admin, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)
        ).fetchone()
        if exists and recreate:
            conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (dbname,),
            )
            conn.execute(f"DROP DATABASE {quote_ident(dbname)}")
        elif exists:
            raise SystemExit(f"staging database already exists: {dbname}; use --recreate")
        conn.execute(f"CREATE DATABASE {quote_ident(dbname)}")
    params["dbname"] = dbname
    return conninfo.make_conninfo(**params)


def copy_sqlite(source: Path, target: Path) -> None:
    if target.exists():
        raise SystemExit(f"sqlite staging target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def apply_schema(dsn: str) -> None:
    import psycopg

    sql = (ROOT / "build_db" / "postgres_schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(dsn) as conn:
        conn.execute(sql)
        conn.commit()


def generate_writes(conn: sqlite3.Connection, cycles: int) -> int:
    stamp = int(time.time())
    ops = 0
    for i in range(cycles):
        paper_id = f"soak_{stamp}_{i:05d}"
        conn.execute(
            "INSERT INTO papers (paper_id, filename, title) VALUES (?, ?, ?)",
            (paper_id, f"{paper_id}.pdf", f"Soak paper {i}"),
        )
        claim_id = f"claim_soak_{stamp}_{i:05d}"
        conn.execute(
            "INSERT INTO claim_cards (claim_id, title, claim_text) VALUES (?, ?, ?)",
            (claim_id, f"Soak claim {i}", f"Body {i}"),
        )
        conn.execute(
            "INSERT INTO watch_items (title, status) VALUES (?, 'new')",
            (f"Soak watch {i}",),
        )
        conn.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES ('ws_soak', ?, 'member')",
            (f"soak_user_{i}",),
        )
        ops += 4
        if i % 2 == 0:
            conn.execute(
                "UPDATE papers SET title = ? WHERE paper_id = ?",
                (f"Soak paper updated {i}", paper_id),
            )
            ops += 1
        if i % 5 == 0:
            conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
            ops += 1
        if i % 7 == 0:
            conn.execute("DELETE FROM claim_cards WHERE claim_id = ?", (claim_id,))
            ops += 1
        conn.commit()
    return ops


def table_counts(conn, pg, tables):
    out = {}
    for name in tables:
        sqlite_count = conn.execute(
            f"SELECT COUNT(*) FROM {quote_ident(name)}"
        ).fetchone()[0]
        row = pg.execute(f"SELECT COUNT(*) FROM {quote_ident(name)}").fetchone()
        pg_count = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
        out[name] = {"sqlite": sqlite_count, "postgres": pg_count}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="SQLite snapshot")
    parser.add_argument("--sqlite-target", required=True)
    parser.add_argument("--pg-admin-dsn", default=os.environ.get("SCIPAL_PG_DSN", ""))
    parser.add_argument("--pg-db", default="scipal_dualwrite_soak")
    parser.add_argument("--cycles", type=int, default=200)
    parser.add_argument("--recreate", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if not args.pg_admin_dsn:
        raise SystemExit("SCIPAL_PG_DSN or --pg-admin-dsn is required")
    source = Path(args.source).resolve()
    if not source.is_file():
        raise SystemExit(f"source snapshot not found: {source}")
    sqlite_target = Path(args.sqlite_target)

    t0 = time.time()
    if args.recreate and sqlite_target.exists():
        sqlite_target.unlink()
    copy_sqlite(source, sqlite_target)
    sqlite_conn = sqlite3.connect(sqlite_target)
    sqlite_conn.row_factory = sqlite3.Row
    install(sqlite_conn, DEFAULT_TABLES)

    pg_dsn = create_staging_db(args.pg_admin_dsn, args.pg_db, args.recreate)
    apply_schema(pg_dsn)

    import psycopg

    seed_tables = ["papers", "claim_cards", "watch_items", "memberships"]
    seed = run_etl(
        sqlite_target,
        PostgresCopyWriter(pg_dsn),
        tables=seed_tables,
    )
    if any(item.status != "ok" for item in seed.tables):
        raise SystemExit(f"seed ETL failed: {[vars(x) for x in seed.tables if x.status != 'ok']}")

    pg = psycopg.connect(pg_dsn)
    try:
        ops = generate_writes(sqlite_conn, args.cycles)
        replay_start = time.time()
        applied = failed = 0
        while True:
            report = replay(sqlite_conn, pg, limit=200)
            applied += report["applied"]
            failed += report["failed"]
            if report["pending"] == 0:
                break
            if report["selected"] == 0:
                break
        replay_seconds = time.time() - replay_start
        tables = seed_tables
        counts = table_counts(sqlite_conn, pg, tables)
        mismatches = [name for name, item in counts.items() if item["sqlite"] != item["postgres"]]
        pending = sqlite_conn.execute(
            "SELECT COUNT(*) FROM dual_write_outbox WHERE processed_at IS NULL"
        ).fetchone()[0]
        bad = failed or pending or mismatches
        result = {
            "source": str(source),
            "sqlite_target": str(sqlite_target),
            "pg_database": args.pg_db,
            "cycles": args.cycles,
            "operations": ops,
            "applied": applied,
            "failed": failed,
            "pending": pending,
            "replay_seconds": round(replay_seconds, 2),
            "total_seconds": round(time.time() - t0, 2),
            "tables": counts,
            "mismatches": mismatches,
            "status": "degraded" if bad else "ok",
        }
    finally:
        pg.close()
        sqlite_conn.close()

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
