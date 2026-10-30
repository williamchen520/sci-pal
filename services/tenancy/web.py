"""Request-scoped workspace resolution and scoped-table migration."""

from __future__ import annotations

import os
import sqlite3

from flask import request, session

from .service import DATABASE_PATH, DEFAULT_WORKSPACE_ID, authorize, list_workspaces

SCOPED_TABLES = ("papers", "notes", "favorites")


def auth_required() -> bool:
    return os.environ.get("SCIPAL_AUTH_REQUIRED", "").strip().lower() in {"1", "true", "yes"}


def ensure_workspace_scoping(conn: sqlite3.Connection) -> None:
    """Add workspace_id to legacy tables without rewriting their rows."""
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for table in SCOPED_TABLES:
        if table not in tables:
            continue
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "workspace_id" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN workspace_id TEXT DEFAULT '{DEFAULT_WORKSPACE_ID}'"
            )
    conn.commit()


def resolve_workspace(*, default: str | None = None, db_path=DATABASE_PATH) -> str | None:
    """Return the active workspace for this request.

    Single-user deployments keep working without a session: when
    SCIPAL_AUTH_REQUIRED is unset the default workspace is used.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None if auth_required() else (default or DEFAULT_WORKSPACE_ID)
    requested = session.get("workspace_id") or request.headers.get("X-SciPal-Workspace")
    if requested and authorize(user_id, requested, "read_workspace", db_path=db_path):
        session["workspace_id"] = requested
        return requested
    workspaces = list_workspaces(user_id, db_path=db_path)
    if not workspaces:
        return None
    workspace_id = workspaces[0]["workspace_id"]
    session["workspace_id"] = workspace_id
    return workspace_id
