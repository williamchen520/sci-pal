"""Personal notes scoped to a workspace."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from config.settings import DATABASE_PATH

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS notes (
        note_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL DEFAULT 'ws_default',
        paper_id TEXT,
        para_id TEXT,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_notes_workspace_user ON notes(workspace_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_notes_paper ON notes(paper_id)",
)


def ensure_notes_schema(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "notes" not in tables:
        for statement in SCHEMA:
            conn.execute(statement)
    else:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(notes)")}
        if "workspace_id" not in columns:
            conn.execute("ALTER TABLE notes ADD COLUMN workspace_id TEXT DEFAULT 'ws_default'")
    conn.commit()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_notes_schema(conn)
    return conn


def paper_in_workspace(conn: sqlite3.Connection, paper_id: str, workspace_id: str) -> bool:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "papers" not in tables:
        return False
    columns = {row[1] for row in conn.execute("PRAGMA table_info(papers)")}
    if "workspace_id" not in columns:
        conn.execute("ALTER TABLE papers ADD COLUMN workspace_id TEXT DEFAULT 'ws_default'")
        conn.commit()
    return bool(
        conn.execute(
            "SELECT 1 FROM papers WHERE paper_id = ? AND workspace_id = ?",
            (paper_id, workspace_id),
        ).fetchone()
    )


def list_notes(
    workspace_id: str,
    user_id: str,
    *,
    paper_id: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict]:
    conn = _connect(db_path)
    try:
        sql = (
            "SELECT note_id, paper_id, para_id, content, created_at, updated_at "
            "FROM notes WHERE workspace_id = ? AND user_id = ?"
        )
        params: list[str] = [workspace_id, user_id]
        if paper_id:
            sql += " AND paper_id = ?"
            params.append(paper_id)
        sql += " ORDER BY updated_at DESC, note_id"
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def create_note(
    workspace_id: str,
    user_id: str,
    content: str,
    *,
    paper_id: str | None = None,
    para_id: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")
    conn = _connect(db_path)
    try:
        if paper_id and not paper_in_workspace(conn, paper_id, workspace_id):
            raise PermissionError("paper not found in workspace")
        note_id = f"note_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO notes (note_id, user_id, workspace_id, paper_id, para_id, content) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, user_id, workspace_id, paper_id, para_id, content),
        )
        conn.commit()
        row = conn.execute(
            "SELECT note_id, paper_id, para_id, content, created_at, updated_at "
            "FROM notes WHERE note_id = ?",
            (note_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_note(
    note_id: str,
    workspace_id: str,
    user_id: str,
    content: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "UPDATE notes SET content = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE note_id = ? AND workspace_id = ? AND user_id = ?",
            (content, note_id, workspace_id, user_id),
        )
        conn.commit()
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT note_id, paper_id, para_id, content, created_at, updated_at "
            "FROM notes WHERE note_id = ?",
            (note_id,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def delete_note(
    note_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> bool:
    conn = _connect(db_path)
    try:
        cursor = conn.execute(
            "DELETE FROM notes WHERE note_id = ? AND workspace_id = ? AND user_id = ?",
            (note_id, workspace_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
