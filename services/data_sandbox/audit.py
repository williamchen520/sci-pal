"""Metadata-only audit log for the data sandbox (no raw values, PostgreSQL only)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def file_digest(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log_event(
    *,
    owner: str,
    project_id: str,
    action: str,
    artifact_id: Optional[str] = None,
    kind: Optional[str] = None,
    provider: Optional[str] = None,
    path: Optional[Path] = None,
    detail: str = "",
) -> None:
    """Append one metadata event; never store file contents."""
    from services.db.pg_pool import pg_connection

    size = path.stat().st_size if path and path.exists() else 0
    digest = file_digest(path) if path and path.exists() else ""
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO data_audit "
            "(owner, project_id, action, artifact_id, kind, provider, bytes, sha256, detail, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                owner, project_id, action, artifact_id, kind, provider,
                size, digest, detail[:500], datetime.now(timezone.utc).isoformat(),
            ),
        )
        pg.commit()
    finally:
        pg.close()


def list_events(
    owner: str, project_id: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    from services.db.pg_pool import pg_connection

    pg = pg_connection()
    try:
        if project_id:
            rows = pg.execute(
                "SELECT * FROM data_audit WHERE owner = %s AND project_id = %s "
                "ORDER BY id DESC LIMIT %s",
                (owner, project_id, limit),
            ).fetchall()
        else:
            rows = pg.execute(
                "SELECT * FROM data_audit WHERE owner = %s ORDER BY id DESC LIMIT %s",
                (owner, limit),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
