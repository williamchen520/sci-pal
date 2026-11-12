"""Platform library registry (scipal_core).

This is platform metadata only. Code payloads live in scipal_code; document
payloads live in scipal_docs; nothing here stores vectors or file contents.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from services.db.pg_pool import core_connection

VALID_KINDS = {"literature", "docs", "code", "data"}
VALID_VISIBILITY = {"private", "workspace", "public"}
SECRET_KEYS = ("token", "password", "secret", "credential", "private_key")


class LibraryError(ValueError):
    pass


def _row(row) -> dict[str, Any]:
    return {
        "library_id": row["library_id"],
        "owner_user_id": row["owner_user_id"],
        "workspace_id": row["workspace_id"],
        "kind": row["kind"],
        "name": row["name"],
        "visibility": row["visibility"],
        "status": row["status"],
        "module_id": row["module_id"],
        "config": row["config"] or {},
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


def _clean_config(config: dict[str, Any] | None) -> dict[str, Any]:
    value = dict(config or {})
    if any(key.lower() in SECRET_KEYS for key in value):
        raise LibraryError("library config must not contain secrets; use the credential store")
    return value


def create_library(
    *,
    owner_user_id: str,
    workspace_id: str,
    kind: str,
    name: str,
    module_id: str | None = None,
    visibility: str = "private",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    kind = (kind or "").strip()
    name = (name or "").strip()
    if kind not in VALID_KINDS:
        raise LibraryError(f"invalid kind: {kind}")
    if not name or len(name) > 120:
        raise LibraryError("name must be 1-120 characters")
    if visibility not in VALID_VISIBILITY:
        raise LibraryError(f"invalid visibility: {visibility}")
    module = (module_id or kind).strip()
    if module != kind and not (kind == "code" and module == "code"):
        raise LibraryError("module_id must match kind in v1")
    config = _clean_config(config)
    library_id = "lib_" + uuid.uuid4().hex[:12]
    pg = core_connection()
    try:
        row = pg.execute(
            """
            INSERT INTO libraries
              (library_id, owner_user_id, workspace_id, kind, name,
               visibility, status, module_id, config)
            VALUES (%s,%s,%s,%s,%s,%s,'registered',%s,%s::jsonb)
            RETURNING *
            """,
            (
                library_id,
                owner_user_id,
                workspace_id,
                kind,
                name,
                visibility,
                module,
                json.dumps(config, ensure_ascii=False),
            ),
        ).fetchone()
        pg.commit()
        return _row(row)
    except Exception as exc:
        pg.rollback()
        if "duplicate key" in str(exc).lower():
            raise LibraryError("a library with this name already exists in the workspace") from None
        raise
    finally:
        pg.close()


def list_libraries(*, workspace_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        if kind:
            rows = pg.execute(
                "SELECT * FROM libraries WHERE workspace_id=%s AND kind=%s "
                "AND status <> 'deleted' ORDER BY created_at DESC",
                (workspace_id, kind),
            ).fetchall()
        else:
            rows = pg.execute(
                "SELECT * FROM libraries WHERE workspace_id=%s AND status <> 'deleted' "
                "ORDER BY created_at DESC",
                (workspace_id,),
            ).fetchall()
        return [_row(row) for row in rows]
    finally:
        pg.close()


def get_library(library_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT * FROM libraries WHERE library_id=%s AND status <> 'deleted'",
            (library_id,),
        ).fetchone()
        return _row(row) if row else None
    finally:
        pg.close()


def set_status(library_id: str, status: str) -> dict[str, Any] | None:
    if status not in {"registered", "creating", "indexing", "ready", "failed"}:
        raise LibraryError("invalid status")
    pg = core_connection()
    try:
        row = pg.execute(
            "UPDATE libraries SET status=%s, updated_at=now() "
            "WHERE library_id=%s AND status <> 'deleted' RETURNING *",
            (status, library_id),
        ).fetchone()
        pg.commit()
        return _row(row) if row else None
    finally:
        pg.close()


def delete_library(library_id: str) -> bool:
    pg = core_connection()
    try:
        row = pg.execute(
            "UPDATE libraries SET status='deleted', updated_at=now() "
            "WHERE library_id=%s AND status <> 'deleted' RETURNING library_id",
            (library_id,),
        ).fetchone()
        pg.commit()
        return bool(row)
    finally:
        pg.close()
