"""P4 metadata dual-write (SQLite primary, PostgreSQL shadow).

Design:
  * SQLite stays the primary database.
  * Triggers append changed row keys to ``dual_write_outbox``.
  * A replay worker upserts/deletes the same rows in PostgreSQL.
  * FTS tables are never replicated; P3 showed FTS is not cut over.

The outbox is intentionally append-only. Application writes never wait for PG.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from services.db.etl import quote_ident

OUTBOX = "dual_write_outbox"

DEFAULT_TABLES = (
    "papers",
    "sections",
    "paragraphs",
    "sentences",
    "figures",
    "tables",
    "citations",
    "sentence_links",
    "paper_links",
    "claim_cards",
    "claim_card_evidence",
    "claim_card_events",
    "watch_items",
    "watch_profiles",
    "watch_runs",
    "watch_seen",
    # Tenancy is PG-primary since 2026-11-02 and deliberately excluded from
    # outbox replication; SQLite is a mirror, not a source of truth.
    "review_projects",
    "review_events",
)

# SQLite type/value coercion for columns whose PostgreSQL type differs.
COLUMN_COERCIONS = {
    ("citations", "year"): str,
}


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    pk: tuple[str, ...]

    @property
    def key_fields(self) -> tuple[str, ...]:
        return self.pk


def _table_columns(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(row[1] for row in conn.execute(f"PRAGMA table_info({quote_ident(table)})"))


def _primary_key(conn: sqlite3.Connection, table: str) -> tuple[str, ...]:
    rows = conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    pk = sorted((row[5], row[1]) for row in rows if row[5])
    return tuple(name for _, name in pk)


def discover_tables(
    conn: sqlite3.Connection, names: Optional[Sequence[str]] = None
) -> List[TableSpec]:
    available = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        if row[0] and row[0] != OUTBOX and "_fts" not in row[0]
    }
    selected = list(names) if names else list(DEFAULT_TABLES)
    specs = []
    for name in selected:
        if name not in available:
            continue
        pk = _primary_key(conn, name)
        if not pk:
            continue
        specs.append(TableSpec(name, _table_columns(conn, name), pk))
    return specs


def ensure_outbox(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {OUTBOX} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            op TEXT NOT NULL,
            key_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        )
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{OUTBOX}_pending "
        f"ON {OUTBOX} (processed_at, id)"
    )


def _key_expr(spec: TableSpec, prefix: str) -> str:
    parts = [f"'{col}', {prefix}.{quote_ident(col)}" for col in spec.pk]
    return "json_object(" + ", ".join(parts) + ")"


def install_triggers(conn: sqlite3.Connection, specs: Sequence[TableSpec]) -> List[str]:
    installed = []
    for spec in specs:
        for suffix in ("ai", "au", "ad"):
            conn.execute(f"DROP TRIGGER IF EXISTS dualwrite_{spec.name}_{suffix}")
        key_new = _key_expr(spec, "NEW")
        key_old = _key_expr(spec, "OLD")
        table = quote_ident(spec.name)
        upsert_sql = (
            f"INSERT INTO {OUTBOX} (table_name, op, key_json, created_at) "
            f"VALUES ('{spec.name}', 'upsert', {key_new}, CURRENT_TIMESTAMP);"
        )
        delete_sql = (
            f"INSERT INTO {OUTBOX} (table_name, op, key_json, created_at) "
            f"VALUES ('{spec.name}', 'delete', {key_old}, CURRENT_TIMESTAMP);"
        )
        conn.execute(
            f"CREATE TRIGGER dualwrite_{spec.name}_ai AFTER INSERT ON {table} BEGIN {upsert_sql} END"
        )
        conn.execute(
            f"CREATE TRIGGER dualwrite_{spec.name}_au AFTER UPDATE ON {table} BEGIN {upsert_sql} END"
        )
        conn.execute(
            f"CREATE TRIGGER dualwrite_{spec.name}_ad AFTER DELETE ON {table} BEGIN {delete_sql} END"
        )
        installed.append(spec.name)
    return installed


def outbox_stats(conn: sqlite3.Connection) -> dict:
    pending = conn.execute(
        f"SELECT COUNT(*) FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    oldest = conn.execute(
        f"SELECT MIN(created_at) FROM {OUTBOX} WHERE processed_at IS NULL"
    ).fetchone()[0]
    return {"pending": pending, "oldest_pending": oldest}


def _row_for_key(
    conn: sqlite3.Connection, spec: TableSpec, key: Dict[str, Any]
) -> Optional[sqlite3.Row]:
    where = " AND ".join(f"{quote_ident(col)} = ?" for col in spec.pk)
    return conn.execute(
        f"SELECT {', '.join(quote_ident(col) for col in spec.columns)} "
        f"FROM {quote_ident(spec.name)} WHERE {where}",
        tuple(key[col] for col in spec.pk),
    ).fetchone()


def _upsert_sql(spec: TableSpec) -> str:
    cols = [col for col in spec.columns]
    col_sql = ", ".join(quote_ident(col) for col in cols)
    params = ", ".join(["%s"] * len(cols))
    pk_sql = ", ".join(quote_ident(col) for col in spec.pk)
    updates = [col for col in cols if col not in spec.pk]
    if updates:
        set_sql = ", ".join(
            f"{quote_ident(col)} = EXCLUDED.{quote_ident(col)}" for col in updates
        )
        conflict = f"DO UPDATE SET {set_sql}"
    else:
        conflict = "DO NOTHING"
    return (
        f"INSERT INTO {quote_ident(spec.name)} ({col_sql}) VALUES ({params}) "
        f"ON CONFLICT ({pk_sql}) {conflict}"
    )


def _coerced(spec: TableSpec, col: str, value: Any) -> Any:
    fn = COLUMN_COERCIONS.get((spec.name, col))
    if fn is not None and value is not None:
        return fn(value)
    return value


def _apply_one(conn: sqlite3.Connection, pg, spec: TableSpec, op: str, key: dict) -> None:
    row = _row_for_key(conn, spec, key)
    where = " AND ".join(f"{quote_ident(col)} = %s" for col in spec.pk)
    if op == "delete" or row is None:
        pg.execute(
            f"DELETE FROM {quote_ident(spec.name)} WHERE {where}",
            tuple(key[col] for col in spec.pk),
        )
        return
    row_map = dict(zip(spec.columns, row))
    values = tuple(_coerced(spec, col, row_map[col]) for col in spec.columns)
    pg.execute(_upsert_sql(spec), values)


def replay(
    conn: sqlite3.Connection,
    pg,
    *,
    limit: int = 100,
    dry_run: bool = False,
) -> dict:
    ensure_outbox(conn)
    pending = conn.execute(
        f"SELECT id, table_name, op, key_json FROM {OUTBOX} "
        "WHERE processed_at IS NULL ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    specs = {spec.name: spec for spec in discover_tables(conn)}
    applied = failed = 0
    for row_id, table, op, key_json in pending:
        spec = specs.get(table)
        if spec is None:
            conn.execute(
                f"UPDATE {OUTBOX} SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                ("unknown table", row_id),
            )
            failed += 1
            continue
        try:
            key = json.loads(key_json)
            if not dry_run:
                _apply_one(conn, pg, spec, op, key)
                pg.commit()
            conn.execute(
                f"UPDATE {OUTBOX} SET processed_at = CURRENT_TIMESTAMP, attempts = attempts + 1 "
                "WHERE id = ?",
                (row_id,),
            )
            applied += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the batch
            try:
                pg.rollback()
            except Exception:  # noqa: BLE001
                pass
            conn.execute(
                f"UPDATE {OUTBOX} SET attempts = attempts + 1, last_error = ? WHERE id = ?",
                (str(exc)[:500], row_id),
            )
            failed += 1
    conn.commit()
    return {"selected": len(pending), "applied": applied, "failed": failed, **outbox_stats(conn)}


def install(conn: sqlite3.Connection, names: Optional[Sequence[str]] = None) -> dict:
    ensure_outbox(conn)
    specs = discover_tables(conn, names)
    installed = install_triggers(conn, specs)
    conn.commit()
    return {"installed": installed, "outbox": outbox_stats(conn)}
