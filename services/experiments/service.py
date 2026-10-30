"""Experiment records: owner-private, project/workspace scoped."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import DATABASE_PATH
from services.tenancy.permissions import audit
from services.tenancy.service import verify_password


class ProtocolNotFound(ValueError):
    """Experiment must reference an imported protocol."""


STATUSES = ("planned", "running", "completed", "failed", "abandoned")
REQUEST_STATUSES = ("pending", "approved", "denied", "expired", "revoked")

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
        current_revision INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_experiments_project ON experiments(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_experiments_owner ON experiments(workspace_id, owner_user_id)",
    """
    CREATE TABLE IF NOT EXISTS experiment_access_requests (
        request_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        requester_user_id TEXT NOT NULL,
        owner_user_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        scope TEXT NOT NULL DEFAULT 'read',
        created_at TEXT NOT NULL,
        decided_at TEXT,
        expires_at TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_exp_requests_experiment ON experiment_access_requests(experiment_id)",
    """
    CREATE TABLE IF NOT EXISTS experiment_revisions (
        revision_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        content TEXT NOT NULL,
        hash TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (experiment_id, revision)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS experiment_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        actor_user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        revision INTEGER,
        detail TEXT,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_exp_revisions_experiment ON experiment_revisions(experiment_id)",
    "CREATE INDEX IF NOT EXISTS idx_exp_audit_experiment ON experiment_audit(experiment_id)",
    """
    CREATE TABLE IF NOT EXISTS experiment_signatures (
        signature_id TEXT PRIMARY KEY,
        experiment_id TEXT NOT NULL,
        workspace_id TEXT NOT NULL,
        revision INTEGER NOT NULL,
        signer_user_id TEXT NOT NULL,
        meaning TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        signature_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_exp_signatures_experiment ON experiment_signatures(experiment_id)",
)


def ensure_experiments_schema(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA:
        conn.execute(statement)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(experiments)")}
    if "current_revision" not in columns:
        conn.execute(
            "ALTER TABLE experiments ADD COLUMN current_revision INTEGER NOT NULL DEFAULT 1"
        )
    conn.commit()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_experiments_schema(conn)
    return conn


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _project_access(conn: sqlite3.Connection, project_id: str, workspace_id: str, user_id: str) -> bool:
    project = conn.execute(
        "SELECT 1 FROM projects WHERE project_id = ? AND workspace_id = ?",
        (project_id, workspace_id),
    ).fetchone()
    if not project:
        return False
    member = conn.execute(
        "SELECT 1 FROM memberships WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id),
    ).fetchone()
    if not member:
        return False
    return bool(
        conn.execute(
            "SELECT 1 FROM project_members WHERE project_id = ? AND user_id = ?",
            (project_id, user_id),
        ).fetchone()
    )


def _workspace_role(conn: sqlite3.Connection, workspace_id: str, user_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM memberships WHERE workspace_id = ? AND user_id = ? AND status = 'active'",
        (workspace_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def _protocol_exists(conn: sqlite3.Connection, protocol_id: str) -> bool:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "protocol_imports" not in tables:
        return False
    return bool(
        conn.execute("SELECT 1 FROM protocol_imports WHERE protocol_id = ?", (protocol_id,)).fetchone()
    )


def _active_approval(
    conn: sqlite3.Connection, experiment_id: str, workspace_id: str, user_id: str
) -> sqlite3.Row | None:
    now = _now().isoformat()
    return conn.execute(
        "SELECT * FROM experiment_access_requests "
        "WHERE experiment_id = ? AND workspace_id = ? AND requester_user_id = ? "
        "AND status = 'approved' AND expires_at IS NOT NULL AND expires_at > ? "
        "ORDER BY decided_at DESC LIMIT 1",
        (experiment_id, workspace_id, user_id, now),
    ).fetchone()


def _snapshot(row: sqlite3.Row | dict) -> dict:
    return {
        "title": row["title"],
        "status": row["status"],
        "protocol_id": row["protocol_id"],
        "protocol_version": row["protocol_version"],
        "content": row["content"],
    }


def _revision_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_revision(
    conn: sqlite3.Connection,
    experiment_id: str,
    workspace_id: str,
    revision: int,
    snapshot: dict,
    actor_user_id: str,
) -> None:
    conn.execute(
        "INSERT INTO experiment_revisions "
        "(revision_id, experiment_id, workspace_id, revision, content, hash, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            f"rev_{uuid.uuid4().hex}",
            experiment_id,
            workspace_id,
            revision,
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            _revision_hash(snapshot),
            actor_user_id,
            _now().isoformat(),
        ),
    )


def _write_audit(
    conn: sqlite3.Connection,
    experiment_id: str,
    workspace_id: str,
    actor_user_id: str,
    action: str,
    revision: int | None,
    detail: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO experiment_audit "
        "(experiment_id, workspace_id, actor_user_id, action, revision, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (experiment_id, workspace_id, actor_user_id, action, revision, detail, _now().isoformat()),
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
    protocol_id: str,
    protocol_version: str,
    status: str = "planned",
    content: str = "",
    db_path: str | Path = DATABASE_PATH,
) -> dict:
    title = (title or "").strip()
    protocol_id = (protocol_id or "").strip()
    protocol_version = (protocol_version or "").strip()
    if not title:
        raise ValueError("title is required")
    if not protocol_id or not protocol_version:
        raise ValueError("protocol_id and protocol_version are required")
    if status not in STATUSES:
        raise ValueError("invalid status")
    conn = _connect(db_path)
    try:
        if not _project_access(conn, project_id, workspace_id, user_id):
            raise PermissionError("project access denied")
        if not _protocol_exists(conn, protocol_id):
            raise ProtocolNotFound("protocol not found")
        experiment_id = f"exp_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO experiments "
            "(experiment_id, project_id, workspace_id, owner_user_id, title, status, "
            "protocol_id, protocol_version, content, current_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
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
        snapshot = {
            "title": title,
            "status": status,
            "protocol_id": protocol_id,
            "protocol_version": protocol_version,
            "content": content,
        }
        _write_revision(conn, experiment_id, workspace_id, 1, snapshot, user_id)
        _write_audit(conn, experiment_id, workspace_id, user_id, "create", 1)
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
            "SELECT * FROM experiments WHERE experiment_id = ? AND workspace_id = ?",
            (experiment_id, workspace_id),
        ).fetchone()
        if not row:
            return None
        if row["owner_user_id"] == user_id:
            return dict(row)
        if _active_approval(conn, experiment_id, workspace_id, user_id):
            audit(workspace_id, user_id, "pi.read", target=experiment_id, db_path=db_path)
            return dict(row)
        return None
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
        current = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ? AND workspace_id = ? "
            "AND owner_user_id = ?",
            (experiment_id, workspace_id, user_id),
        ).fetchone()
        if not current:
            return None
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
            revision = int(current["current_revision"] or 1) + 1
            conn.execute(
                f"UPDATE experiments SET {assignments}, current_revision = ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE experiment_id = ? AND workspace_id = ? AND owner_user_id = ?",
                [*fields.values(), revision, experiment_id, workspace_id, user_id],
            )
            snapshot = _snapshot(current)
            snapshot.update(fields)
            _write_revision(conn, experiment_id, workspace_id, revision, snapshot, user_id)
            _write_audit(
                conn,
                experiment_id,
                workspace_id,
                user_id,
                "update",
                revision,
                ",".join(sorted(fields)),
            )
            conn.commit()
        return get_experiment(experiment_id, workspace_id, user_id, db_path=db_path)
    finally:
        conn.close()


def list_revisions(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict] | None:
    if not get_experiment(experiment_id, workspace_id, user_id, db_path=db_path):
        return None
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT revision_id, revision, hash, created_by, created_at, content "
            "FROM experiment_revisions WHERE experiment_id = ? AND workspace_id = ? "
            "ORDER BY revision DESC",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_audit(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict] | None:
    if not get_experiment(experiment_id, workspace_id, user_id, db_path=db_path):
        return None
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, actor_user_id, action, revision, detail, created_at "
            "FROM experiment_audit WHERE experiment_id = ? AND workspace_id = ? "
            "ORDER BY id",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_access_request(
    experiment_id: str,
    workspace_id: str,
    requester_user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        if _workspace_role(conn, workspace_id, requester_user_id) != "pi":
            return None
        experiment = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ? AND workspace_id = ?",
            (experiment_id, workspace_id),
        ).fetchone()
        if not experiment or experiment["owner_user_id"] == requester_user_id:
            return None
        existing = conn.execute(
            "SELECT 1 FROM experiment_access_requests WHERE experiment_id = ? "
            "AND requester_user_id = ? AND status IN ('pending','approved')",
            (experiment_id, requester_user_id),
        ).fetchone()
        if existing:
            return None
        request_id = f"req_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO experiment_access_requests "
            "(request_id, experiment_id, workspace_id, requester_user_id, owner_user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                request_id,
                experiment_id,
                workspace_id,
                requester_user_id,
                experiment["owner_user_id"],
                _now().isoformat(),
            ),
        )
        conn.commit()
        audit(workspace_id, requester_user_id, "pi.request", target=experiment_id, db_path=db_path)
        row = conn.execute(
            "SELECT * FROM experiment_access_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_access_requests(
    experiment_id: str,
    workspace_id: str,
    actor_user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict] | None:
    conn = _connect(db_path)
    try:
        experiment = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ? AND workspace_id = ?",
            (experiment_id, workspace_id),
        ).fetchone()
        if not experiment:
            return None
        if experiment["owner_user_id"] == actor_user_id:
            rows = conn.execute(
                "SELECT * FROM experiment_access_requests WHERE experiment_id = ? "
                "ORDER BY created_at DESC",
                (experiment_id,),
            ).fetchall()
        elif _workspace_role(conn, workspace_id, actor_user_id) == "pi":
            rows = conn.execute(
                "SELECT * FROM experiment_access_requests WHERE experiment_id = ? "
                "AND requester_user_id = ? ORDER BY created_at DESC",
                (experiment_id, actor_user_id),
            ).fetchall()
        else:
            return []
        return [dict(row) for row in rows]
    finally:
        conn.close()


def decide_access_request(
    experiment_id: str,
    request_id: str,
    workspace_id: str,
    owner_user_id: str,
    approve: bool,
    *,
    hours: int = 24,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        experiment = conn.execute(
            "SELECT 1 FROM experiments WHERE experiment_id = ? AND workspace_id = ? "
            "AND owner_user_id = ?",
            (experiment_id, workspace_id, owner_user_id),
        ).fetchone()
        if not experiment:
            return None
        request = conn.execute(
            "SELECT * FROM experiment_access_requests WHERE request_id = ? "
            "AND experiment_id = ? AND workspace_id = ? AND status = 'pending'",
            (request_id, experiment_id, workspace_id),
        ).fetchone()
        if not request:
            return None
        now = _now()
        status = "approved" if approve else "denied"
        expires_at = (now + timedelta(hours=max(1, hours))).isoformat() if approve else None
        conn.execute(
            "UPDATE experiment_access_requests SET status = ?, decided_at = ?, expires_at = ? "
            "WHERE request_id = ?",
            (status, now.isoformat(), expires_at, request_id),
        )
        conn.commit()
        audit(
            workspace_id,
            owner_user_id,
            "pi.approve" if approve else "pi.deny",
            target=experiment_id,
            detail=request_id,
            db_path=db_path,
        )
        row = conn.execute(
            "SELECT * FROM experiment_access_requests WHERE request_id = ?", (request_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def sign_experiment(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    password: str,
    *,
    meaning: str = "author",
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    """Sign the current revision after re-authentication."""
    if meaning not in {"author", "reviewer", "approver"}:
        raise ValueError("invalid signature meaning")
    conn = _connect(db_path)
    try:
        experiment = conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ? AND workspace_id = ? "
            "AND owner_user_id = ?",
            (experiment_id, workspace_id, user_id),
        ).fetchone()
        if not experiment:
            return None
        user = conn.execute(
            "SELECT password_hash FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            raise PermissionError("re-authentication failed")
        revision = int(experiment["current_revision"] or 1)
        rev = conn.execute(
            "SELECT * FROM experiment_revisions WHERE experiment_id = ? AND revision = ?",
            (experiment_id, revision),
        ).fetchone()
        if not rev:
            return None
        now = _now().isoformat()
        signature_id = f"sig_{uuid.uuid4().hex}"
        signature_hash = hashlib.sha256(
            f"{rev['hash']}|{user_id}|{meaning}|{now}".encode("utf-8")
        ).hexdigest()
        conn.execute(
            "INSERT INTO experiment_signatures "
            "(signature_id, experiment_id, workspace_id, revision, signer_user_id, "
            "meaning, record_hash, signature_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                signature_id,
                experiment_id,
                workspace_id,
                revision,
                user_id,
                meaning,
                rev["hash"],
                signature_hash,
                now,
            ),
        )
        _write_audit(conn, experiment_id, workspace_id, user_id, "sign", revision, meaning)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM experiment_signatures WHERE signature_id = ?", (signature_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_signatures(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict] | None:
    if not get_experiment(experiment_id, workspace_id, user_id, db_path=db_path):
        return None
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT signature_id, revision, signer_user_id, meaning, record_hash, "
            "signature_hash, created_at FROM experiment_signatures "
            "WHERE experiment_id = ? AND workspace_id = ? ORDER BY created_at",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

