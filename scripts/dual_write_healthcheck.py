#!/usr/bin/env python3
"""P4 dual-write health check.

Read-only: reports outbox lag, failed rows, trigger count, and per-table row
counts between SQLite and PostgreSQL. Exit non-zero on a threshold breach.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.paths import DB_PATH  # noqa: E402
from services.db.dual_write import DEFAULT_TABLES, OUTBOX, discover_tables  # noqa: E402
from services.db.etl import quote_ident  # noqa: E402


TENANCY_TABLES = {
    "users": (("user_id",), ("user_id", "username", "email", "display_name", "password_hash", "status", "is_admin")),
    "workspaces": (("workspace_id",), ("workspace_id", "name", "owner_user_id")),
    "memberships": (("workspace_id", "user_id"), ("workspace_id", "user_id", "role", "status")),
}


def _sqlite_rows(conn, table, columns):
    placeholders = ", ".join(quote_ident(column) for column in columns)
    return [tuple(row) for row in conn.execute(f"SELECT {placeholders} FROM {quote_ident(table)}")]


def _pg_rows(pg, table, columns):
    placeholders = ", ".join(quote_ident(column) for column in columns)
    rows = pg.execute(f"SELECT {placeholders} FROM {quote_ident(table)}").fetchall()
    return [tuple(row.values()) if isinstance(row, dict) else tuple(row) for row in rows]


def tenancy_drift(conn: sqlite3.Connection, pg) -> dict:
    """Row-level SQLite/PG comparison for tenancy tables, if present."""
    available = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    report = {}
    for table, (key, columns) in TENANCY_TABLES.items():
        if table not in available:
            report[table] = {"available": False, "drift": False}
            continue
        try:
            sq = _sqlite_rows(conn, table, columns)
            pg_rows = _pg_rows(pg, table, columns)
        except Exception as exc:  # noqa: BLE001 - absent PG table is not a drift signal here
            report[table] = {"available": False, "drift": False, "error": str(exc)}
            continue
        key_index = [columns.index(column) for column in key]
        sq_map = {tuple(row[i] for i in key_index): row for row in sq}
        pg_map = {tuple(row[i] for i in key_index): row for row in pg_rows}
        only_sqlite = sorted(set(sq_map) - set(pg_map))
        only_pg = sorted(set(pg_map) - set(sq_map))
        changed = [k for k in sorted(set(sq_map) & set(pg_map)) if sq_map[k] != pg_map[k]]
        report[table] = {
            "available": True,
            "sqlite": len(sq),
            "postgres": len(pg_rows),
            "only_sqlite": [dict(zip(key, k)) for k in only_sqlite[:20]],
            "only_pg": [dict(zip(key, k)) for k in only_pg[:20]],
            "changed": [dict(zip(key, k)) for k in changed[:20]],
            "drift": bool(only_sqlite or only_pg or changed),
        }
    return report


def collect(conn: sqlite3.Connection, pg, tables=None) -> dict:
    names = list(tables or DEFAULT_TABLES)
    specs = discover_tables(conn, names)
    counts = []
    for spec in specs:
        sqlite_count = conn.execute(
            f"SELECT COUNT(*) FROM {quote_ident(spec.name)}"
        ).fetchone()[0]
        row = pg.execute(f"SELECT COUNT(*) FROM {quote_ident(spec.name)}").fetchone()
        pg_count = int(next(iter(row.values())) if isinstance(row, dict) else row[0])
        counts.append(
            {
                "table": spec.name,
                "sqlite": sqlite_count,
                "postgres": pg_count,
                "match": sqlite_count == pg_count,
            }
        )
    pending = conn.execute(
        f"SELECT COUNT(*) FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    failed = conn.execute(
        f"SELECT COUNT(*) FROM {OUTBOX} WHERE processed_at IS NULL AND last_error IS NOT NULL"
    ).fetchone()[0]
    oldest = conn.execute(
        f"SELECT MIN(created_at) FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    age = conn.execute(
        f"SELECT (julianday('now') - julianday(MIN(created_at))) * 86400 "
        f"FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    triggers = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_%'"
    ).fetchone()[0]
    return {
        "pending": pending,
        "failed": failed,
        "oldest_pending": oldest,
        "pending_age_seconds": round(age, 1) if age is not None else None,
        "triggers": triggers,
        "tables": counts,
        "mismatches": [c["table"] for c in counts if not c["match"]],
        "tenancy_drift": tenancy_drift(conn, pg),
    }


def _send_alert(webhook: str, report: dict) -> None:
    payload = {
        "status": report.get("status"),
        "pending": report.get("pending"),
        "failed": report.get("failed"),
        "mismatches": report.get("mismatches", []),
        "tenancy_drift": {
            table: item.get("drift")
            for table, item in (report.get("tenancy_drift") or {}).items()
        },
    }
    text = json.dumps(payload, ensure_ascii=False)
    if not webhook:
        print(f"ALERT degraded: {text}", file=sys.stderr, flush=True)
        return
    request = urllib.request.Request(
        webhook,
        data=text.encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "SciPal/0.1"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            print(f"alert sent: {response.status}", file=sys.stderr, flush=True)
    except Exception as exc:  # noqa: BLE001 - alerting must not mask health result
        print(f"alert failed: {exc}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--max-pending", type=int, default=100)
    parser.add_argument("--max-age", type=float, default=300.0)
    parser.add_argument("--out", default="")
    parser.add_argument("--alert-webhook", default=os.environ.get("SCIPAL_HEALTH_ALERT_WEBHOOK", ""))
    args = parser.parse_args()

    dsn = os.environ.get("SCIPAL_PG_DSN", "").strip()
    if not dsn:
        print("SCIPAL_PG_DSN is required", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("psycopg is required", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    pg = psycopg.connect(dsn)
    try:
        report = collect(conn, pg)
    finally:
        pg.close()
        conn.close()

    bad = (
        report["failed"] > 0
        or report["pending"] > args.max_pending
        or (report["pending_age_seconds"] or 0) > args.max_age
        or bool(report["mismatches"])
        or any(item.get("drift") for item in report.get("tenancy_drift", {}).values())
    )
    report["status"] = "degraded" if bad else "ok"
    if bad:
        _send_alert(args.alert_webhook, report)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
