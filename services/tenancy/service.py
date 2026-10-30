"""Local accounts, workspaces and role checks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import DATABASE_PATH

from .schema import ROLES, ensure_schema

DEFAULT_WORKSPACE_ID = "ws_default"
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")
ROLE_SET = set(ROLES)

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


def _connect(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


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
            password.encode("utf-8"),
            salt=_unb64(salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(expected, _unb64(digest))
    except (ValueError, TypeError):
        return False


def _audit(conn: sqlite3.Connection, workspace_id: str | None, actor: str | None, action: str, target: str | None = None, detail: str | None = None) -> None:
    conn.execute(
        "INSERT INTO tenancy_audit (workspace_id, actor_user_id, action, target, detail) VALUES (?, ?, ?, ?, ?)",
        (workspace_id, actor, action, target, detail),
    )


def create_user(
    username: str,
    password: str,
    *,
    email: str | None = None,
    display_name: str | None = None,
    is_admin: bool = False,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> dict[str, Any]:
    username = (username or "").strip()
    if not USERNAME_RE.match(username):
        raise TenancyError("username must be 3-64 characters: letters, digits, _ . -")
    if email and "@" not in email:
        raise TenancyError("invalid email")
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise TenancyError("username already exists")
        user_id = f"user_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO users (user_id, username, email, display_name, password_hash, status, is_admin) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (user_id, username, email, display_name or username, hash_password(password), int(is_admin)),
        )
        _audit(conn, None, user_id, "user.create", user_id)
        conn.commit()
        return {
            "user_id": user_id,
            "username": username,
            "email": email,
            "display_name": display_name or username,
            "is_admin": bool(is_admin),
        }
    finally:
        conn.close()


def authenticate(
    username: str,
    password: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> dict[str, Any] | None:
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT user_id, username, email, display_name, password_hash, status, is_admin "
            "FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
        if not row or row["status"] != "active":
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "display_name": row["display_name"],
            "is_admin": bool(row["is_admin"]),
        }
    finally:
        conn.close()


def bootstrap_default_workspace(
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> dict[str, Any]:
    """Create the default workspace for existing single-user data.

    Existing users are enrolled as members. If there are no users, a disabled
    local bootstrap user is created so migration never invents a login secret.
    """
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT workspace_id FROM workspaces WHERE workspace_id = ?",
            (DEFAULT_WORKSPACE_ID,),
        ).fetchone()
        created = False
        if not row:
            user = conn.execute("SELECT user_id FROM users ORDER BY created_at LIMIT 1").fetchone()
            if not user:
                bootstrap_id = "user_local"
                conn.execute(
                    "INSERT INTO users (user_id, username, email, display_name, password_hash, status, is_admin) "
                    "VALUES (?, 'local', NULL, 'Local user', NULL, 'pending', 0)",
                    (bootstrap_id,),
                )
                owner = bootstrap_id
            else:
                owner = user["user_id"]
            conn.execute(
                "INSERT INTO workspaces (workspace_id, name, owner_user_id) VALUES (?, ?, ?)",
                (DEFAULT_WORKSPACE_ID, "Default workspace", owner),
            )
            created = True
        else:
            owner = conn.execute(
                "SELECT owner_user_id FROM workspaces WHERE workspace_id = ?",
                (DEFAULT_WORKSPACE_ID,),
            ).fetchone()["owner_user_id"]
        users = conn.execute("SELECT user_id FROM users").fetchall()
        for user in users:
            if user["user_id"] == owner:
                role = "owner"
            else:
                role = "member"
            conn.execute(
                "INSERT OR IGNORE INTO memberships (workspace_id, user_id, role) VALUES (?, ?, ?)",
                (DEFAULT_WORKSPACE_ID, user["user_id"], role),
            )
        _audit(conn, DEFAULT_WORKSPACE_ID, owner, "workspace.bootstrap", DEFAULT_WORKSPACE_ID)
        conn.commit()
        return {"workspace_id": DEFAULT_WORKSPACE_ID, "owner_user_id": owner, "created": created}
    finally:
        conn.close()


def create_workspace(
    name: str,
    owner_user_id: str,
    *,
    workspace_id: str | None = None,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise TenancyError("workspace name is required")
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (owner_user_id,)).fetchone():
            raise TenancyError("owner user does not exist")
        wid = workspace_id or f"ws_{uuid.uuid4().hex}"
        if conn.execute("SELECT 1 FROM workspaces WHERE workspace_id = ?", (wid,)).fetchone():
            raise TenancyError("workspace already exists")
        conn.execute(
            "INSERT INTO workspaces (workspace_id, name, owner_user_id) VALUES (?, ?, ?)",
            (wid, name, owner_user_id),
        )
        conn.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES (?, ?, 'owner')",
            (wid, owner_user_id),
        )
        _audit(conn, wid, owner_user_id, "workspace.create", wid)
        conn.commit()
        return {"workspace_id": wid, "name": name, "owner_user_id": owner_user_id}
    finally:
        conn.close()


def add_member(
    workspace_id: str,
    user_id: str,
    role: str,
    *,
    actor_user_id: str | None = None,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> Membership:
    if role not in ROLE_SET:
        raise TenancyError(f"invalid role: {role}")
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        if not conn.execute("SELECT 1 FROM workspaces WHERE workspace_id = ?", (workspace_id,)).fetchone():
            raise TenancyError("workspace does not exist")
        if not conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone():
            raise TenancyError("user does not exist")
        conn.execute(
            "INSERT INTO memberships (workspace_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(workspace_id, user_id) DO UPDATE SET role = excluded.role",
            (workspace_id, user_id, role),
        )
        _audit(conn, workspace_id, actor_user_id, "membership.upsert", f"{workspace_id}/{user_id}", role)
        conn.commit()
        return Membership(workspace_id, user_id, role, "active")
    finally:
        conn.close()


def get_membership(
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> Membership | None:
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT workspace_id, user_id, role, status FROM memberships "
            "WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
            (workspace_id, user_id),
        ).fetchone()
        if not row:
            return None
        return Membership(row["workspace_id"], row["user_id"], row["role"], row["status"])
    finally:
        conn.close()


def list_members(
    workspace_id: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT m.user_id, u.username, u.display_name, m.role, m.status "
            "FROM memberships m JOIN users u ON u.user_id = m.user_id "
            "WHERE m.workspace_id = ? ORDER BY m.created_at, u.username",
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_workspaces(
    user_id: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> list[dict[str, Any]]:
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        rows = conn.execute(
            "SELECT w.workspace_id, w.name, w.owner_user_id, m.role "
            "FROM workspaces w JOIN memberships m ON m.workspace_id = w.workspace_id "
            "WHERE m.user_id = ? AND m.status = 'active' ORDER BY w.created_at, w.name",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_user_by_username(
    username: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> dict[str, Any] | None:
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT user_id, username, display_name, status FROM users WHERE username = ?",
            ((username or "").strip(),),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user(
    user_id: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> dict[str, Any] | None:
    conn = _connect(db_path)
    try:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT user_id, username, display_name, email, status, is_admin "
            "FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def authorize(
    user_id: str,
    workspace_id: str,
    action: str,
    *,
    db_path: str | os.PathLike[str] = DATABASE_PATH,
) -> bool:
    if action not in ACTIONS:
        raise TenancyError(f"unknown action: {action}")
    membership = get_membership(workspace_id, user_id, db_path=db_path)
    if not membership:
        return False
    return action in ROLE_PERMISSIONS[membership.role]
