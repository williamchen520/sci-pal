"""Experiment records: owner-private, project/workspace scoped."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from config.settings import DATABASE_PATH

STATUSES = ("planned", "running", "completed", "failed", "abandoned")

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        owner_user_id TEXT NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'planned',
        protocol_id TEXT,
        protocol_version TEXT,
        content TEXT DEFAULT '',
        data_class TEXT NOT NULL DEFAULT 'private',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_experiments_project ON experiments(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_experiments_owner ON experiments(workspace_id, owner_user_id)",
)


def ensure_experiments_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA:
        conn.execute(statement)
    conn.commit()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_experiments_schema(conn)
    return conn


def _project_access(conn: sqlite3.Connection, project_id: str, workspace_id: str, user_id: str) -> bool:
    project = conn.execute(
        "SELECT 1 FROM projects WHERE project_id = ? AND workspace_id = ?",
        (project_id, workspace_id),
    ).fetchone()
    if not project:
        return False
    workspace_member = conn.execute(
        "SELECT 1 FROM memberships WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id),
    ).fetchone()
    if not workspace_member:
        return False
    return bool(
        conn.execute(
            "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        ).fetchone()
    )


def list_experiments(
    project_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict] | None:
    conn = _connect(db_path)
    try:
        if not _project_access(conn, project_id, workspace_id, user_id):
            return None
        rows = conn.execute(
            "SELECT * FROM experiments WHERE project_id = ? AND workspace_id = ? "
            "AND owner_user_id = ? ORDER BY updated_at DESC, experiment_id",
            (project_id, workspace_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_experiment(
    project_id: str,
    workspace_id: str,
    user_id: str,
    title: str,
    *,
    status: str = "planned",
    protocol_id: str | None = None,
    protocol_version: str | None = None,
    content: str = "",
    db_path: str | Path = DATABASE_PATH,
) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if status not in STATUSES:
        raise ValueError("invalid status")
    conn = _connect(db_path)
    try:
        if not _project_access(conn, project_id, workspace_id, user_id):
            raise PermissionError("project access denied")
        experiment_id = f"exp_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO experiments "
            "(experiment_id, project_id, workspace_id, owner_user_id, title, status, "
            "protocol_id, protocol_version, content) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                experiment_id,
                project_id,
                workspace_id,
                user_id,
                title,
                status,
                protocol_id,
                protocol_version,
                content,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_experiment(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ? AND workspace_id = ? "
            "AND owner_user_id = ?",
            (experiment_id, workspace_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_experiment(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    content: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        fields = {}
        if title is not None:
            if not title.strip():
                raise ValueError("title is required")
            fields["title"] = title.strip()
        if status is not None:
            if status not in STATUSES:
                raise ValueError("invalid status")
            fields["status"] = status
        if content is not None:
            fields["content"] = content
        if fields:
            assignments = ", ".join(f"{key} = ?" for key in fields)
            conn.execute(
                f"UPDATE experiments SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE experiment_id = ? AND workspace_id = ? AND owner_user_id = ?",
                [*fields.values(), experiment_id, workspace_id, user_id],
            )
            conn.commit()
        return get_experiment(experiment_id, workspace_id, user_id, db_path=db_path)
    finally:
        conn.close()
