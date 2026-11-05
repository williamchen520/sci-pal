"""PostgreSQL write adapter for experiments (G3.6b, create first)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from services.db.pg_pool import pg_connection
from services.experiments import pg_read, pg_writes
from services.experiments.service import STATUSES, ProtocolNotFound, _revision_hash


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
