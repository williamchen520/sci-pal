"""Review project webhook notifications."""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def _sqlite_allowed() -> bool:
    import os

    return os.environ.get("SCIPAL_REVIEW_WEBHOOKS_ALLOW_SQLITE", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def _pg_enabled() -> bool:
    return not _sqlite_allowed()


def _pg():
    from services.db.pg_pool import owner_connection

    return owner_connection()


def add_webhook(
    conn: sqlite3.Connection, project_id: str, url: str, events: str = "*", secret: str = ""
) -> int:
    if _pg_enabled():
        pg = _pg()
        try:
            row = pg.execute(
                "INSERT INTO review_webhooks (project_id, url, events, secret, active, created_at) "
                "VALUES (%s, %s, %s, %s, 1, %s) RETURNING id",
                (project_id, url, events, secret, datetime.now(timezone.utc).isoformat()),
            ).fetchone()
            pg.commit()
            return int(row["id"])
        finally:
            pg.close()
    cursor = conn.execute(
        "INSERT INTO review_webhooks (project_id, url, events, secret, active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (project_id, url, events, secret, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_webhooks(conn: sqlite3.Connection, project_id: str) -> List[Dict]:
    if _pg_enabled():
        pg = _pg()
        try:
            rows = pg.execute(
                "SELECT id, url, events, active FROM review_webhooks "
                "WHERE project_id = %s ORDER BY id",
                (project_id,),
            ).fetchall()
            return [
                {"id": row["id"], "url": row["url"], "events": row["events"], "active": bool(row["active"])}
                for row in rows
            ]
        finally:
            pg.close()
    rows = conn.execute(
        "SELECT id, url, events, active FROM review_webhooks "
        "WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    return [
        {"id": row[0], "url": row[1], "events": row[2], "active": bool(row[3])}
        for row in rows
    ]


def delete_webhook(conn: sqlite3.Connection, project_id: str, webhook_id: int) -> None:
    if _pg_enabled():
        pg = _pg()
        try:
            pg.execute(
                "DELETE FROM review_webhooks WHERE project_id = %s AND id = %s",
                (project_id, webhook_id),
            )
            pg.commit()
        finally:
            pg.close()
        return
    conn.execute(
        "DELETE FROM review_webhooks WHERE project_id = ? AND id = ?",
        (project_id, webhook_id),
    )
    conn.commit()


def _post(hook: Dict, payload: Dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        hook["url"],
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-SciPal-Secret": hook.get("secret") or "",
        },
        method="POST",
    )
    urllib.request.urlopen(request, timeout=5).read()


def notify(
    db_path: Path | str,
    project_id: str,
    event: str,
    payload: Dict,
    sender: Optional[Callable[[Dict, Dict], None]] = None,
) -> int:
    if _pg_enabled():
        pg = _pg()
        try:
            hooks = pg.execute(
                "SELECT id, url, events, secret FROM review_webhooks "
                "WHERE project_id = %s AND active = 1",
                (project_id,),
            ).fetchall()
        finally:
            pg.close()
        body = {"project_id": project_id, "event": event, "data": payload}
        delivered = 0
        for hook in hooks:
            allowed = {item.strip() for item in (hook["events"] or "*").split(",")}
            if "*" not in allowed and event not in allowed:
                continue
            try:
                (sender or _post)(dict(hook), body)
                delivered += 1
            except Exception:  # noqa: BLE001
                pass
        return delivered
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    delivered = 0
    try:
        hooks = conn.execute(
            "SELECT id, url, events, secret FROM review_webhooks "
            "WHERE project_id = ? AND active = 1",
            (project_id,),
        ).fetchall()
        body = {"project_id": project_id, "event": event, "data": payload}
        for hook in hooks:
            allowed = {item.strip() for item in (hook["events"] or "*").split(",")}
            if "*" not in allowed and event not in allowed:
                continue
            hook_dict = dict(hook)
            try:
                (sender or _post)(hook_dict, body)
                delivered += 1
            except Exception:  # noqa: BLE001
                pass
    finally:
        conn.close()
    return delivered
