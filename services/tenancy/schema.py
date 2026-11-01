"""Schema for users, workspaces, memberships and tenancy audit."""

from __future__ import annotations

import sqlite3
import threading

ROLES = ("owner", "pi", "member", "viewer")

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        workspace_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        owner_user_id TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memberships (
        workspace_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (workspace_id, user_id),
        FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tenancy_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace_id TEXT,
        actor_user_id TEXT,
        action TEXT NOT NULL,
        target TEXT,
        detail TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_memberships_user ON memberships(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_tenancy_audit_workspace ON tenancy_audit(workspace_id)",
)

USER_COLUMNS = {
    "display_name": "TEXT",
    "password_hash": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'active'",
    "is_admin": "INTEGER NOT NULL DEFAULT 0",
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


_SCHEMA_READY: set[str] = set()
_SCHEMA_LOCK = threading.Lock()


def _db_key(conn: sqlite3.Connection) -> str:
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        return str(row[2]) if row and row[2] else f"memory:{id(conn)}"
    except sqlite3.DatabaseError:
        return f"memory:{id(conn)}"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tenancy tables and add missing user columns.

    Idempotent and cached per database path: a request must not run DDL every
    time it resolves a workspace or checks membership.
    """
    key = _db_key(conn)
    with _SCHEMA_LOCK:
        if key in _SCHEMA_READY:
            return
        _ensure_schema_uncached(conn)
        _SCHEMA_READY.add(key)


def _ensure_schema_uncached(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    existing = _columns(conn, "users")
    for name, definition in USER_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {definition}")
    for statement in SCHEMA:
        conn.execute(statement)
    _scope_legacy_tables(conn)
    conn.commit()


def _scope_legacy_tables(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for table in ("papers", "notes", "favorites"):
        if table not in tables:
            continue
        columns = _columns(conn, table)
        if "workspace_id" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN workspace_id TEXT DEFAULT 'ws_default'"
            )
