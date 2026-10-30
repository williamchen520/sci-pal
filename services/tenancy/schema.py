"""Schema for users, workspaces, memberships and tenancy audit."""

from __future__ import annotations

import sqlite3

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


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tenancy tables and add missing user columns.

    Idempotent: safe to call on the existing single-user database.
    """
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
