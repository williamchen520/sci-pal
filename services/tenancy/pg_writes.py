"""PostgreSQL-primary tenancy writes.

Used only when SCIPAL_TENANCY_WRITE_BACKEND=postgres. SQLite remains a mirror
for legacy direct readers and FTS/Chroma; callers fall back to SQLite on error.
"""

from __future__ import annotations

import os
from typing import Any


class PGWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_TENANCY_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["SCIPAL_PG_DSN"], row_factory=dict_row)


def _ensure_audit_sequence(pg) -> None:
    row = pg.execute("SELECT pg_get_serial_sequence('tenancy_audit', 'id')").fetchone()
    seq = next(iter(row.values())) if row else None
    if seq:
        pg.execute(
            "SELECT setval(%s, COALESCE((SELECT max(id) FROM tenancy_audit), 0) + 1, false)",
            (seq,),
        )


def _audit(pg, workspace_id, actor, action, target=None, detail=None) -> None:
    _ensure_audit_sequence(pg)
    pg.execute(
        "INSERT INTO tenancy_audit (workspace_id, actor_user_id, action, target, detail) "
        "VALUES (%s, %s, %s, %s, %s)",
        (workspace_id, actor, action, target, detail),
    )


def create_user(
    *,
    username: str,
    password_hash: str,
    email: str | None,
    display_name: str,
    is_admin: bool,
) -> dict[str, Any]:
    import uuid

    user_id = f"user_{uuid.uuid4().hex}"
    with _connect() as pg:
        if pg.execute("SELECT 1 FROM users WHERE username = %s", (username,)).fetchone():
            raise PGWriteError("username already exists")
        pg.execute(
            "INSERT INTO users (user_id, username, email, display_name, password_hash, status, is_admin) "
            "VALUES (%s, %s, %s, %s, %s, 'active', %s)",
            (user_id, username, email, display_name, password_hash, int(is_admin)),
        )
        _audit(pg, None, user_id, "user.create", user_id)
    return {
        "user_id": user_id,
        "username": username,
        "email": email,
        "display_name": display_name,
        "is_admin": bool(is_admin),
    }


def create_workspace(*, name: str, owner_user_id: str, workspace_id: str) -> dict[str, Any]:
    with _connect() as pg:
        if not pg.execute("SELECT 1 FROM users WHERE user_id = %s", (owner_user_id,)).fetchone():
            raise PGWriteError("owner user does not exist")
        if pg.execute("SELECT 1 FROM workspaces WHERE workspace_id = %s", (workspace_id,)).fetchone():
            raise PGWriteError("workspace already exists")
        pg.execute(
            "INSERT INTO workspaces (workspace_id, name, owner_user_id) VALUES (%s, %s, %s)",
            (workspace_id, name, owner_user_id),
        )
        pg.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES (%s, %s, 'owner')",
            (workspace_id, owner_user_id),
        )
        _audit(pg, workspace_id, owner_user_id, "workspace.create", workspace_id)
    return {"workspace_id": workspace_id, "name": name, "owner_user_id": owner_user_id}


def add_member(
    *,
    workspace_id: str,
    user_id: str,
    role: str,
    actor_user_id: str | None,
) -> dict[str, Any]:
    with _connect() as pg:
        if not pg.execute(
            "SELECT 1 FROM workspaces WHERE workspace_id = %s", (workspace_id,)
        ).fetchone():
            raise PGWriteError("workspace does not exist")
        if not pg.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,)).fetchone():
            raise PGWriteError("user does not exist")
        pg.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES (%s, %s, %s) "
            "ON CONFLICT (workspace_id, user_id) DO UPDATE SET role = EXCLUDED.role",
            (workspace_id, user_id, role),
        )
        _audit(pg, workspace_id, actor_user_id, "membership.upsert", f"{workspace_id}/{user_id}", role)
    return {
        "workspace_id": workspace_id,
        "user_id": user_id,
        "role": role,
        "status": "active",
    }


def list_members(workspace_id: str) -> list[dict[str, Any]]:
    with _connect() as pg:
        rows = pg.execute(
            "SELECT m.user_id, u.username, u.display_name, m.role, m.status "
            "FROM memberships m JOIN users u ON u.user_id = m.user_id "
            "WHERE m.workspace_id = %s ORDER BY m.created_at, u.username",
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]
