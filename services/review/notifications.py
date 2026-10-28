"""Review project webhook notifications."""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def add_webhook(
    conn: sqlite3.Connection, project_id: str, url: str, events: str = "*", secret: str = ""
) -> int:
    cursor = conn.execute(
        "INSERT INTO review_webhooks (project_id, url, events, secret, active, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?)",
        (project_id, url, events, secret, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_webhooks(conn: sqlite3.Connection, project_id: str) -> List[Dict]:
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
