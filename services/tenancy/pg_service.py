"""PostgreSQL-backed tenancy implementation (runtime default)."""

from __future__ import annotations

import base64
import re
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import DATABASE_PATH

from .schema import ROLES
from . import pg_writes

DEFAULT_WORKSPACE_ID = "ws_default"

ACTIONS = (
    "read_workspace",
    "write_own",
    "write_workspace",
    "read_all",
    "copy",
    "manage_members",
    "manage_workspace",
)
ROLE_PERMISSIONS = {
    "owner": set(ACTIONS),
    "pi": {"read_workspace", "write_own", "read_all", "copy"},
    "member": {"read_workspace", "write_own"},
    "viewer": {"read_workspace"},
}


class TenancyError(ValueError):
    """Invalid tenancy operation."""


@dataclass(frozen=True)
class Membership:
    workspace_id: str
    user_id: str
    role: str
    status: str


def _admin():
    from services.db.pg_pool import auth_connection

    return auth_connection()


def _require():
    if not pg_writes.enabled():
        raise TenancyError("tenancy write backend unavailable")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise TenancyError("password must contain at least 8 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded or not isinstance(password, str):
        return False
    try:
        scheme, n, r, p, salt, digest = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        expected = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p)
        )
        return hmac.compare_digest(expected, _unb64(digest))
    except (ValueError, TypeError):
        return False


def authenticate(username: str, password: str):
    with _admin() as pg:
        row = pg.execute(
            "SELECT user_id, username, email, display_name, password_hash, status, is_admin "
            "FROM users WHERE username = %s",
            ((username or "").strip(),),
        ).fetchone()
    if not row or row["status"] != "active" or not verify_password(password, row["password_hash"]):
        return None
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "is_admin": bool(row["is_admin"]),
    }


def create_user(username: str, password: str, *, email=None, display_name=None, is_admin=False, db_path=DATABASE_PATH):
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$", (username or "").strip()):
        raise TenancyError("username must be 3-64 characters: letters, digits, _ . -")
    if email and "@" not in email:
        raise TenancyError("invalid email")
    _require()
    try:
        return pg_writes.create_user(
            username=username.strip(),
            password_hash=hash_password(password),
            email=email,
            display_name=display_name or username.strip(),
            is_admin=is_admin,
        )
    except TenancyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TenancyError("tenancy write backend unavailable") from exc


def bootstrap_default_workspace(*, db_path=DATABASE_PATH):
    pg = _admin()
    try:
        row = pg.execute(
            "SELECT workspace_id, owner_user_id FROM workspaces WHERE workspace_id=%s",
            (DEFAULT_WORKSPACE_ID,),
        ).fetchone()
        if row:
            return {"workspace_id": row["workspace_id"], "owner_user_id": row["owner_user_id"], "created": False}
        user = pg.execute("SELECT user_id FROM users ORDER BY created_at LIMIT 1").fetchone()
        owner = user["user_id"] if user else "user_local"
        if not user:
            pg.execute(
                "INSERT INTO users (user_id,username,display_name,status,is_admin) "
                "VALUES (%s,'local','Local user','pending',0) ON CONFLICT DO NOTHING",
                (owner,),
            )
        pg.execute(
            "INSERT INTO workspaces (workspace_id,name,owner_user_id) "
            "VALUES (%s,'Default workspace',%s) ON CONFLICT DO NOTHING",
            (DEFAULT_WORKSPACE_ID, owner),
        )
        for item in pg.execute("SELECT user_id FROM users").fetchall():
            role = "owner" if item["user_id"] == owner else "member"
            pg.execute(
                "INSERT INTO memberships (workspace_id,user_id,role_id) VALUES (%s,%s,%s) "
                "ON CONFLICT (workspace_id,user_id) DO UPDATE SET role=EXCLUDED.role",
                (DEFAULT_WORKSPACE_ID, item["user_id"], role),
            )
        pg.commit()
        return {"workspace_id": DEFAULT_WORKSPACE_ID, "owner_user_id": owner, "created": True}
    finally:
        pg.close()


def create_workspace(name: str, owner_user_id: str, *, workspace_id=None, db_path=DATABASE_PATH):
    name = (name or "").strip()
    if not name:
        raise TenancyError("workspace name is required")
    _require()
    try:
        return pg_writes.create_workspace(
            name=name, owner_user_id=owner_user_id, workspace_id=workspace_id or f"ws_{uuid.uuid4().hex}"
        )
    except TenancyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TenancyError("tenancy write backend unavailable") from exc


def add_member(workspace_id: str, user_id: str, role: str, *, actor_user_id=None, db_path=DATABASE_PATH):
    if role not in set(ROLES):
        raise TenancyError(f"invalid role: {role}")
    _require()
    try:
        result = pg_writes.add_member(
            workspace_id=workspace_id, user_id=user_id, role=role, actor_user_id=actor_user_id
        )
    except TenancyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise TenancyError("tenancy write backend unavailable") from exc
    return Membership(result["workspace_id"], result["user_id"], result["role"], result["status"])


def get_membership(workspace_id: str, user_id: str, *, db_path=DATABASE_PATH):
    with _admin() as pg:
        row = pg.execute(
            "SELECT workspace_id,user_id,role_id AS role,status FROM memberships "
            "WHERE workspace_id=%s AND user_id=%s AND status='active'",
            (workspace_id, user_id),
        ).fetchone()
    return Membership(row["workspace_id"], row["user_id"], row["role"], row["status"]) if row else None


def list_members(workspace_id: str, *, db_path=DATABASE_PATH):
    return pg_writes.list_members(workspace_id)


def list_workspaces(user_id: str, *, db_path=DATABASE_PATH):
    with _admin() as pg:
        rows = pg.execute(
            "SELECT w.workspace_id,w.name,w.owner_user_id,m.role_id AS role FROM workspaces w "
            "JOIN memberships m ON m.workspace_id=w.workspace_id "
            "WHERE m.user_id=%s AND m.status='active' ORDER BY w.created_at,w.name",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_by_username(username: str, *, db_path=DATABASE_PATH):
    with _admin() as pg:
        row = pg.execute(
            "SELECT user_id,username,display_name,status FROM users WHERE username=%s",
            ((username or "").strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_password_hash(user_id: str, *, db_path=DATABASE_PATH):
    with _admin() as pg:
        row = pg.execute("SELECT password_hash FROM users WHERE user_id=%s", (user_id,)).fetchone()
    return row["password_hash"] if row else None


def get_user(user_id: str, *, db_path=DATABASE_PATH):
    with _admin() as pg:
        row = pg.execute(
            "SELECT user_id,username,display_name,email,status,is_admin FROM users WHERE user_id=%s",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def authorize(user_id: str, workspace_id: str, action: str, *, db_path=DATABASE_PATH):
    if action not in ACTIONS:
        raise TenancyError(f"unknown action: {action}")
    membership = get_membership(workspace_id, user_id, db_path=db_path)
    return bool(membership and action in ROLE_PERMISSIONS[membership.role])
