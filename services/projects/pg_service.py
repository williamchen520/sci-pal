"""PostgreSQL project service (G3.10e1)."""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from services.db.pg_pool import pg_connection
from services.tenancy.permissions import pi_can_copy


def enabled() -> bool:
    return os.environ.get("SCIPAL_PROJECTS_BACKEND", "").strip().lower() in {
        "postgres", "postgresql", "pg", "1", "true"
    }


def _pg():
    from services.db.pg_pool import pg_connection
    from services.db.tenant_pilot import set_search_path

    pg = pg_connection()
    set_search_path(pg, "projects")
    return pg


def _workspace_role(pg, workspace_id: str, user_id: str) -> Optional[str]:
    row = pg.execute(
        "SELECT role FROM memberships WHERE workspace_id = %s AND user_id = %s AND status = 'active'",
        (workspace_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def _can_see_all(role: Optional[str]) -> bool:
    return role in {"owner", "pi"}


def _project_role(pg, project_id: str, user_id: str) -> Optional[str]:
    row = pg.execute(
        "SELECT role FROM project_members WHERE project_id = %s AND user_id = %s",
        (project_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def list_projects(workspace_id: str, user_id: str) -> List[Dict[str, Any]]:
    pg = _pg()
    try:
        role = _workspace_role(pg, workspace_id, user_id)
        if not role:
            return []
        if _can_see_all(role):
            rows = pg.execute(
                "SELECT * FROM projects WHERE workspace_id = %s ORDER BY updated_at DESC, project_id",
                (workspace_id,),
            ).fetchall()
        else:
            rows = pg.execute(
                "SELECT p.* FROM projects p JOIN project_members m ON m.project_id = p.project_id "
                "WHERE p.workspace_id = %s AND m.user_id = %s ORDER BY p.updated_at DESC, p.project_id",
                (workspace_id, user_id),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def get_project(project_id: str, workspace_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    pg = _pg()
    try:
        role = _workspace_role(pg, workspace_id, user_id)
        if not role:
            return None
        project = pg.execute(
            "SELECT * FROM projects WHERE project_id = %s AND workspace_id = %s",
            (project_id, workspace_id),
        ).fetchone()
        if not project:
            return None
        if not _can_see_all(role) and not _project_role(pg, project_id, user_id):
            return None
        data = dict(project)
        data["members"] = [
            dict(row)
            for row in pg.execute(
                "SELECT m.user_id, u.username, m.role FROM project_members m "
                "JOIN users u ON u.user_id = m.user_id WHERE m.project_id = %s "
                "ORDER BY m.created_at",
                (project_id,),
            ).fetchall()
        ]
        return data
    finally:
        pg.close()


def create_project(
    workspace_id: str,
    owner_user_id: str,
    name: str,
    description: str = "",
    *,
    status: str = "active",
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    pg = _pg()
    try:
        if not _workspace_role(pg, workspace_id, owner_user_id):
            raise PermissionError("workspace access denied")
        project_id = f"project_{uuid.uuid4().hex}"
        pg.execute(
            "INSERT INTO projects (project_id, workspace_id, owner_user_id, name, description, status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (project_id, workspace_id, owner_user_id, name, description, status),
        )
        pg.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, 'owner')",
            (project_id, owner_user_id),
        )
        pg.commit()
    finally:
        pg.close()
    return get_project(project_id, workspace_id, owner_user_id) or {}


def update_project(
    project_id: str,
    workspace_id: str,
    user_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    pg = _pg()
    try:
        project = pg.execute(
            "SELECT * FROM projects WHERE project_id = %s AND workspace_id = %s",
            (project_id, workspace_id),
        ).fetchone()
        if not project:
            return None
        workspace_role = _workspace_role(pg, workspace_id, user_id)
        project_role = _project_role(pg, project_id, user_id)
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
            fields["status"] = status
        if fields:
            assignments = ", ".join(f"{key} = %s" for key in fields)
            pg.execute(
                f"UPDATE projects SET {assignments}, updated_at = now() "
                "WHERE project_id = %s AND workspace_id = %s",
                [*fields.values(), project_id, workspace_id],
            )
            pg.commit()
    finally:
        pg.close()
    return get_project(project_id, workspace_id, user_id)


def add_member(
    project_id: str,
    workspace_id: str,
    actor_user_id: str,
    target_user_id: str,
    role: str = "member",
) -> Optional[Dict[str, Any]]:
    if role not in {"owner", "member", "viewer"}:
        raise ValueError("invalid role")
    pg = _pg()
    try:
        project = pg.execute(
            "SELECT 1 FROM projects WHERE project_id = %s AND workspace_id = %s",
            (project_id, workspace_id),
        ).fetchone()
        if not project:
            return None
        if _project_role(pg, project_id, actor_user_id) != "owner":
            return None
        if not _workspace_role(pg, workspace_id, target_user_id):
            raise ValueError("target user is not in workspace")
        pg.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, %s) "
            "ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role",
            (project_id, target_user_id, role),
        )
        pg.commit()
        return {"project_id": project_id, "user_id": target_user_id, "role": role}
    finally:
        pg.close()

def copy_project(
    project_id: str,
    workspace_id: str,
    actor_user_id: str,
) -> Optional[Dict[str, Any]]:
    pg = _pg()
    try:
        role = _workspace_role(pg, workspace_id, actor_user_id)
        if role not in {"owner", "pi"}:
            return None
        source = pg.execute(
            "SELECT * FROM projects WHERE project_id = %s AND workspace_id = %s",
            (project_id, workspace_id),
        ).fetchone()
        if not source:
            return None
        if role == "pi" and not pi_can_copy(source.get("data_class")):
            return None
        new_id = f"project_{uuid.uuid4().hex}"
        pg.execute(
            "INSERT INTO projects "
            "(project_id, workspace_id, owner_user_id, name, description, status, data_class, copied_from) "
            "VALUES (%s, %s, %s, %s, %s, 'planning', %s, %s)",
            (
                new_id,
                workspace_id,
                actor_user_id,
                f"Copy of {source['name']}",
                source.get("description") or "",
                source.get("data_class") or "internal",
                project_id,
            ),
        )
        pg.execute(
            "INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, 'owner')",
            (new_id, actor_user_id),
        )
        pg.commit()
    finally:
        pg.close()
    return get_project(new_id, workspace_id, actor_user_id)
