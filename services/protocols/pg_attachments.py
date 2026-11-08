"""PostgreSQL protocol run attachments (G3.10e2d)."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from services.db.pg_pool import owner_connection
from services.protocols.service import _now, _text

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_RUN_ATTACHMENT_BYTES = 100 * 1024 * 1024


def _storage_root() -> Path:
    return Path(os.environ.get("SCIPAL_PROTOCOL_STORAGE_ROOT", "/app/data/experiments"))


def add_attachment(run_id: str, filename: str, content_type: str, data: bytes) -> Dict:
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError("file too large (max 20 MB)")
    pg = owner_connection()
    try:
        exists = pg.execute(
            "SELECT 1 FROM protocol_runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        if not exists:
            raise ValueError("run not found")
        used = pg.execute(
            "SELECT COALESCE(SUM(size), 0) AS n FROM protocol_run_files WHERE run_id = %s",
            (run_id,),
        ).fetchone()["n"]
        if used + len(data) > MAX_RUN_ATTACHMENT_BYTES:
            raise ValueError("run attachment quota exceeded (max 100 MB)")
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(filename or "file")).name)[:120]
        safe = safe or "file"
        file_id = "file_" + uuid.uuid4().hex[:12]
        folder = _storage_root() / run_id
        folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{file_id}_{safe}"
        (folder / stored_name).write_bytes(data)
        now = _now()
        pg.execute(
            "INSERT INTO protocol_run_files "
            "(file_id, run_id, filename, stored_name, content_type, size, uploaded_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (file_id, run_id, safe, stored_name, _text(content_type), len(data), now),
        )
        pg.commit()
        return {
            "file_id": file_id,
            "run_id": run_id,
            "filename": safe,
            "content_type": _text(content_type),
            "size": len(data),
            "uploaded_at": now,
        }
    finally:
        pg.close()


def list_attachments(run_id: str) -> List[Dict]:
    pg = owner_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM protocol_run_files WHERE run_id = %s ORDER BY uploaded_at",
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def attachment_path(run_id: str, file_id: str) -> Optional[Path]:
    pg = owner_connection()
    try:
        row = pg.execute(
            "SELECT stored_name FROM protocol_run_files WHERE run_id = %s AND file_id = %s",
            (run_id, file_id),
        ).fetchone()
        if not row:
            return None
        path = _storage_root() / run_id / row["stored_name"]
        return path if path.exists() else None
    finally:
        pg.close()


def delete_attachment(run_id: str, file_id: str) -> bool:
    path = attachment_path(run_id, file_id)
    pg = owner_connection()
    try:
        row = pg.execute(
            "DELETE FROM protocol_run_files WHERE run_id = %s AND file_id = %s RETURNING file_id",
            (run_id, file_id),
        ).fetchone()
        pg.commit()
    finally:
        pg.close()
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    return bool(row)
