"""Review project webhook notifications (PostgreSQL only)."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional


def _pg():
    from services.db.pg_pool import pg_connection
    from services.db.tenant_pilot import set_search_path

    pg = pg_connection()
    set_search_path(pg, "systematic")
    return pg


def add_webhook(conn, project_id: str, url: str, events: str = "*", secret: str = "") -> int:
    # conn is kept for call-site compatibility; storage is PostgreSQL-only.
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


def list_webhooks(conn, project_id: str) -> List[Dict]:
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


def delete_webhook(conn, project_id: str, webhook_id: int) -> None:
    pg = _pg()
    try:
        pg.execute(
            "DELETE FROM review_webhooks WHERE project_id = %s AND id = %s",
            (project_id, webhook_id),
        )
        pg.commit()
    finally:
        pg.close()


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
    db_path,
    project_id: str,
    event: str,
    payload: Dict,
    sender: Optional[Callable[[Dict, Dict], None]] = None,
) -> int:
    # db_path is kept for call-site compatibility; storage is PostgreSQL-only.
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
