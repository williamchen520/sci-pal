"""Projects scoped to a workspace."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from config.settings import DATABASE_PATH

STATUSES = ("planning", "active", "paused", "completed", "archived")

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS projects (
        project_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        owner_user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        data_class TEXT NOT NULL DEFAULT 'internal',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_members (
        project_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (project_id, user_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_projects_workspace ON projects(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id)",
)


def ensure_projects_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA:
        conn.execute(statement)
    conn.commit()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_projects_schema(conn)
    return conn


def _workspace_role(conn: sqlite3.Connection, workspace_id: str, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM memberships WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def _can_see_all(role: str | None) -> bool:
    return role in {"owner", "pi"}


def _project_role(conn: sqlite3.Connection, project_id: str, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def list_projects(workspace_id: str, user_id: str, *, db_path: str | Path = DATABASE_PATH) -> list[dict]:
    conn = _connect(db_path)
    try:
        role = _workspace_role(conn, workspace_id, user_id)
        if not role:
            return []
        if _can_see_all(role):
            rows = conn.execute(
                "SELECT * FROM projects WHERE workspace_id = ? ORDER BY updated_at DESC, project_id",
                (workspace_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT p.* FROM projects p JOIN project_members m ON m.project_id = p.project_id "
                "WHERE p.workspace_id = ? AND m.user_id = ? ORDER BY p.updated_at DESC, p.project_id",
                (workspace_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_project(
    project_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        role = _workspace_role(conn, workspace_id, user_id)
        if not role:
            return None
        project = conn.execute(
            "SELECT * FROM projects WHERE project_id = ? AND workspace_id = ?",
            (project_id, workspace_id),
        ).fetchone()
        if not project:
            return None
        if not _can_see_all(role) and not _project_role(conn, project_id, user_id):
            return None
        data = dict(project)
        data["members"] = [
            dict(row)
            for row in conn.execute(
                "SELECT m.user_id, u.username, m.role FROM project_members m "
                "JOIN users u ON u.user_id = m.user_id WHERE m.project_id = ? ORDER BY m.created_at",
                (project_id,),
            )
        ]
        return data
    finally:
        conn.close()


def create_project(
    workspace_id: str,
    owner_user_id: str,
    name: str,
    description: str = "",
    *,
    status: str = "active",
    db_path: str | Path = DATABASE_PATH,
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    if status not in STATUSES:
        raise ValueError("invalid status")
    conn = _connect(db_path)
    try:
        if not _workspace_role(conn, workspace_id, owner_user_id):
            raise PermissionError("workspace access denied")
        project_id = f"project_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO projects (project_id, workspace_id, owner_user_id, name, description, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, workspace_id, owner_user_id, name, description, status),
        )
        conn.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, 'owner')",
            (project_id, owner_user_id),
        )
        conn.commit()
        return get_project(project_id, workspace_id, owner_user_id, db_path=db_path) or {}
    finally:
        conn.close()


def update_project(
    project_id: str,
    workspace_id: str,
    user_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        project = conn.execute(
            "SELECT * FROM projects WHERE project_id = ? AND workspace_id = ?",
            (project_id, workspace_id),
        ).fetchone()
        if not project:
            return None
        workspace_role = _workspace_role(conn, workspace_id, user_id)
        project_role = _project_role(conn, project_id, user_id)
        if workspace_role != "owner" and project_role != "owner":
            return None
        fields = {}
        if name is not None:
            if not name.strip():
                raise ValueError("name is required")
            fields["name"] = name.strip()
        if description is not None:
            fields["description"] = description
        if status is not None:
            if status not in STATUSES:
                raise ValueError("invalid status")
            fields["status"] = status
        if fields:
            assignments = ", ".join(f"{key} = ?" for key in fields)
            conn.execute(
                f"UPDATE projects SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE project_id = ? AND workspace_id = ?",
                [*fields.values(), project_id, workspace_id],
            )
            conn.commit()
        return get_project(project_id, workspace_id, user_id, db_path=db_path)
    finally:
        conn.close()


def add_member(
    project_id: str,
    workspace_id: str,
    actor_user_id: str,
    target_user_id: str,
    role: str = "member",
    *,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    if role not in {"owner", "member", "viewer"}:
        raise ValueError("invalid role")
    conn = _connect(db_path)
    try:
        project = conn.execute(
            "SELECT 1 FROM projects WHERE project_id = ? AND workspace_id = ?",
            (project_id, workspace_id),
        ).fetchone()
        if not project:
            return None
        if _project_role(conn, project_id, actor_user_id) != "owner":
            return None
        if not _workspace_role(conn, workspace_id, target_user_id):
            raise ValueError("target user is not in workspace")
        conn.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(project_id, user_id) DO UPDATE SET role = excluded.role",
            (project_id, target_user_id, role),
        )
        conn.commit()
        return {"project_id": project_id, "user_id": target_user_id, "role": role}
    finally:
        conn.close()
