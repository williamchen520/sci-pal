"""Import session persistence (single tenant)."""

from __future__ import annotations

import uuid
from typing import Any, Iterable

from services.db.pg_pool import core_connection
from services.imports.detector import detect
from services.imports.router import route


class ImportSessionError(ValueError):
    """Invalid import request."""


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def create_import(
    *,
    tenant_id: str,
    library_id: str,
    origin: str,
    items: Iterable[dict[str, Any]],
    created_by: str = "",
) -> dict[str, Any]:
    rows = list(items)
    if not rows:
        raise ImportSessionError("at least one item is required")
    if len(rows) > 1000:
        raise ImportSessionError("at most 1000 items per import session")
    if origin not in {"manual", "dsh", "api"}:
        raise ImportSessionError(f"invalid origin: {origin}")
    if not tenant_id or not library_id:
        raise ImportSessionError("tenant_id and library_id are required")

    import_id = _new_id("imp")
    prepared = []
    for index, item in enumerate(rows, start=1):
        uri = str(item.get("uri") or "").strip()
        detection = detect(uri)
        routed = route(detection.source_kind)
        status = "quarantined" if routed.lane == "quarantine" else "detected"
        prepared.append(
            {
                "item_id": f"item_{index:04d}",
                "kind": detection.kind,
                "source_kind": detection.source_kind,
                "source_uri": uri,
                "content_hash": str(item.get("content_hash") or ""),
                "status": status,
                "error": "" if status == "detected" else "format not recognized",
            }
        )

    with core_connection() as pg:
        pg.execute(
            "INSERT INTO import_sessions "
            "(import_id,tenant_id,library_id,origin,status,total_items,created_by) "
            "VALUES (%s,%s,%s,%s,'queued',%s,%s)",
            (import_id, tenant_id, library_id, origin, len(prepared), created_by),
        )
        for row in prepared:
            pg.execute(
                "INSERT INTO import_items "
                "(import_id,item_id,kind,source_kind,source_uri,content_hash,status,error) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    import_id,
                    row["item_id"],
                    row["kind"],
                    row["source_kind"],
                    row["source_uri"],
                    row["content_hash"],
                    row["status"],
                    row["error"],
                ),
            )
    return get_import(import_id)


def get_import(import_id: str) -> dict[str, Any]:
    with core_connection() as pg:
        session = pg.execute(
            "SELECT * FROM import_sessions WHERE import_id=%s", (import_id,)
        ).fetchone()
        if not session:
            raise ImportSessionError(f"import not found: {import_id}")
        items = pg.execute(
            "SELECT * FROM import_items WHERE import_id=%s ORDER BY item_id",
            (import_id,),
        ).fetchall()
    result = dict(session)
    result["items"] = [dict(item) for item in items]
    return result


def list_items(import_id: str) -> list[dict[str, Any]]:
    with core_connection() as pg:
        rows = pg.execute(
            "SELECT * FROM import_items WHERE import_id=%s ORDER BY item_id",
            (import_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def retry_items(import_id: str) -> dict[str, Any]:
    with core_connection() as pg:
        rows = pg.execute(
            "SELECT item_id,source_kind FROM import_items "
            "WHERE import_id=%s AND status IN ('failed','quarantined')",
            (import_id,),
        ).fetchall()
        for row in rows:
            routed = route(row["source_kind"])
            if routed.lane == "quarantine":
                continue
            pg.execute(
                "UPDATE import_items SET status='detected', error=NULL, updated_at=now() "
                "WHERE import_id=%s AND item_id=%s",
                (import_id, row["item_id"]),
            )
        pg.execute(
            "UPDATE import_sessions SET status='queued', updated_at=now() WHERE import_id=%s",
            (import_id,),
        )
    return get_import(import_id)


def set_item_status(import_id: str, item_id: str, status: str, error: str = "") -> None:
    allowed = {
        "received",
        "detected",
        "routed",
        "parsed",
        "built",
        "indexed",
        "draft",
        "failed",
        "quarantined",
    }
    if status not in allowed:
        raise ImportSessionError(f"invalid item status: {status}")
    with core_connection() as pg:
        pg.execute(
            "UPDATE import_items SET status=%s,error=%s,updated_at=now() "
            "WHERE import_id=%s AND item_id=%s",
            (status, error or None, import_id, item_id),
        )


def finalize_session(
    import_id: str, *, processed: int, failed: int, status: str
) -> None:
    if status not in {"queued", "running", "review", "completed", "partial", "failed"}:
        raise ImportSessionError(f"invalid session status: {status}")
    with core_connection() as pg:
        pg.execute(
            "UPDATE import_sessions SET status=%s,processed_items=%s,failed_items=%s,"
            "updated_at=now() WHERE import_id=%s",
            (status, processed, failed, import_id),
        )
