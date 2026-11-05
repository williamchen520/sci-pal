"""PostgreSQL write adapter for experiments (G3.6b, create first)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from services.db.pg_pool import pg_connection
from services.experiments import pg_read, pg_writes
from services.experiments.service import (
    STATUSES,
    ProtocolNotFound,
    _revision_hash,
    _snapshot,
    verify_password,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _protocol_exists(pg, protocol_id: str) -> bool:
    return bool(
        pg.execute(
            "SELECT 1 FROM protocol_imports WHERE protocol_id = %s", (protocol_id,)
        ).fetchone()
    )


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

    pg = pg_connection()
    try:
        if not pg_read._project_access(pg, project_id, workspace_id, user_id):
            raise PermissionError("project access denied")
        if not _protocol_exists(pg, protocol_id):
            raise ProtocolNotFound("protocol not found")
    finally:
        pg.close()

    now = _now()
    experiment_id = f"exp_{uuid.uuid4().hex}"
    snapshot = {
        "title": title,
        "status": status,
        "protocol_id": protocol_id,
        "protocol_version": protocol_version,
        "content": content,
    }
    experiment = {
        "experiment_id": experiment_id,
        "project_id": project_id,
        "workspace_id": workspace_id,
        "owner_user_id": user_id,
        "title": title,
        "status": status,
        "protocol_id": protocol_id,
        "protocol_version": protocol_version,
        "content": content,
        "created_at": now,
        "updated_at": now,
    }
    revision = {
        "revision_id": f"rev_{uuid.uuid4().hex}",
        "experiment_id": experiment_id,
        "workspace_id": workspace_id,
        "revision": 1,
        "content": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        "hash": _revision_hash(snapshot),
        "created_by": user_id,
        "created_at": now,
    }
    audit = {
        "experiment_id": experiment_id,
        "workspace_id": workspace_id,
        "actor_user_id": user_id,
        "action": "create",
        "revision": 1,
        "detail": None,
        "created_at": now,
    }
    pg_writes.create_experiment(experiment, revision, audit)
    return pg_read.get_experiment(experiment_id, workspace_id, user_id) or {}

def update_experiment(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    content: str | None = None,
) -> dict | None:
    pg = pg_connection()
    try:
        current = pg.execute(
            "SELECT * FROM experiments WHERE experiment_id = %s AND workspace_id = %s "
            "AND owner_user_id = %s",
            (experiment_id, workspace_id, user_id),
        ).fetchone()
    finally:
        pg.close()
    if not current:
        return None
    current = dict(current)
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
    if not fields:
        return pg_read.get_experiment(experiment_id, workspace_id, user_id)
    revision = int(current.get("current_revision") or 1) + 1
    now = _now()
    snapshot = _snapshot(current)
    snapshot.update(fields)
    revision_row = {
        "revision_id": f"rev_{uuid.uuid4().hex}",
        "experiment_id": experiment_id,
        "workspace_id": workspace_id,
        "revision": revision,
        "content": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        "hash": _revision_hash(snapshot),
        "created_by": user_id,
        "created_at": now,
    }
    audit = {
        "experiment_id": experiment_id,
        "workspace_id": workspace_id,
        "actor_user_id": user_id,
        "action": "update",
        "revision": revision,
        "detail": ",".join(sorted(fields)),
        "created_at": now,
    }
    pg_writes.update_experiment(experiment_id, workspace_id, fields, revision_row, audit)
    return pg_read.get_experiment(experiment_id, workspace_id, user_id)


def sign_experiment(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    password: str,
    *,
    meaning: str = "author",
) -> dict | None:
    if meaning not in {"author", "reviewer", "approver"}:
        raise ValueError("invalid signature meaning")
    pg = pg_connection()
    try:
        experiment = pg.execute(
            "SELECT * FROM experiments WHERE experiment_id = %s AND workspace_id = %s "
            "AND owner_user_id = %s",
            (experiment_id, workspace_id, user_id),
        ).fetchone()
        if not experiment:
            return None
        user = pg.execute(
            "SELECT password_hash FROM users WHERE user_id = %s", (user_id,)
        ).fetchone()
        if not user or not verify_password(password, user.get("password_hash")):
            raise PermissionError("re-authentication failed")
        revision = int(experiment.get("current_revision") or 1)
        rev = pg.execute(
            "SELECT * FROM experiment_revisions WHERE experiment_id = %s AND revision = %s",
            (experiment_id, revision),
        ).fetchone()
        if not rev:
            return None
    finally:
        pg.close()
    now = _now()
    signature_hash = hashlib.sha256(
        f"{rev['hash']}|{user_id}|{meaning}|{now}".encode("utf-8")
    ).hexdigest()
    signature = {
        "signature_id": f"sig_{uuid.uuid4().hex}",
        "experiment_id": experiment_id,
        "workspace_id": workspace_id,
        "revision": revision,
        "signer_user_id": user_id,
        "meaning": meaning,
        "record_hash": rev["hash"],
        "signature_hash": signature_hash,
        "created_at": now,
    }
    audit = {
        "experiment_id": experiment_id,
        "workspace_id": workspace_id,
        "actor_user_id": user_id,
        "action": "sign",
        "revision": revision,
        "detail": meaning,
        "created_at": now,
    }
    pg_writes.create_signature(signature, audit)
    return signature
