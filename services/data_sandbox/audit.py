"""Metadata-only audit log for the data sandbox (no raw values)."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS data_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT,
    project_id TEXT,
    action TEXT,
    artifact_id TEXT,
    kind TEXT,
    provider TEXT,
    bytes INTEGER,
    sha256 TEXT,
    detail TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_data_audit_project
    ON data_audit(owner, project_id, id);
"""


def _db_path() -> Path:
    return Path(os.environ.get("SCIPAL_AUDIT_DB", str(DEFAULT_DB)))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    return conn


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
    size = path.stat().st_size if path and path.exists() else 0
    digest = file_digest(path) if path and path.exists() else ""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO data_audit "
            "(owner, project_id, action, artifact_id, kind, provider, bytes, sha256, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                owner,
                project_id,
                action,
                artifact_id,
                kind,
                provider,
                size,
                digest,
                detail[:500],
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_events(
    owner: str, project_id: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if project_id:
            rows = conn.execute(
                "SELECT * FROM data_audit WHERE owner = ? AND project_id = ? "
                "ORDER BY id DESC LIMIT ?",
                (owner, project_id, limit),
            )
        else:
            rows = conn.execute(
                "SELECT * FROM data_audit WHERE owner = ? ORDER BY id DESC LIMIT ?",
                (owner, limit),
            )
        return [dict(row) for row in rows]
    finally:
        conn.close()
