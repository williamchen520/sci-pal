"""Unified task manager (PostgreSQL only)."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

_subscribers: Dict[str, List] = {}
_lock = threading.Lock()


def _pg_conn():
    from services.db.pg_pool import pg_connection
    from services.db.tenant_pilot import set_search_path

    pg = pg_connection()
    set_search_path(pg, "tasks")
    return pg


def _pg_write(sql: str, params: tuple) -> None:
    pg = _pg_conn()
    try:
        pg.execute(sql, params)
        pg.commit()
    finally:
        pg.close()


def create_task(task_type: str, params: Optional[Dict] = None, task_id: Optional[str] = None) -> str:
    if task_id is None:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()
    _pg_write(
        "INSERT INTO tasks (task_id, type, status, progress_text, progress_pct, params, created_at, started_at) "
        "VALUES (%s,%s,'running','initializing',0,%s,%s,%s) ON CONFLICT (task_id) DO NOTHING",
        (task_id, task_type, json.dumps(params or {}, ensure_ascii=False), now, now),
    )
    _broadcast(task_id, "created", {"task_id": task_id, "type": task_type})
    return task_id


def update_progress(task_id: str, text: str, pct: float = 0):
    _pg_write(
        "UPDATE tasks SET progress_text = %s, progress_pct = %s WHERE task_id = %s AND status = 'running'",
        (text, pct, task_id),
    )
    _broadcast(task_id, "progress", {"text": text, "pct": pct})


def complete_task(task_id: str, result: Any = None):
    now = datetime.now().isoformat()
    _pg_write(
        "UPDATE tasks SET status = 'completed', progress_pct = 100, finished_at = %s, result = %s WHERE task_id = %s",
        (now, json.dumps(result, ensure_ascii=False) if result else None, task_id),
    )
    _broadcast(task_id, "done", {"status": "completed"})


def fail_task(task_id: str, error: str):
    now = datetime.now().isoformat()
    _pg_write(
        "UPDATE tasks SET status = 'failed', finished_at = %s, error = %s WHERE task_id = %s",
        (now, error, task_id),
    )
    _broadcast(task_id, "error", {"error": error})


def cancel_task(task_id: str):
    now = datetime.now().isoformat()
    _pg_write(
        "UPDATE tasks SET status = 'cancelled', finished_at = %s WHERE task_id = %s",
        (now, task_id),
    )
    _broadcast(task_id, "cancelled", {"status": "cancelled"})


def get_task(task_id: str) -> Optional[Dict]:
    pg = _pg_conn()
    try:
        row = pg.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        pg.close()


def list_tasks(task_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    pg = _pg_conn()
    try:
        query = "SELECT * FROM tasks WHERE 1=1"
        args = []
        if task_type:
            query += " AND type = %s"
            args.append(task_type)
        if status:
            query += " AND status = %s"
            args.append(status)
        query += " ORDER BY created_at DESC LIMIT %s"
        args.append(limit)
        return [dict(row) for row in pg.execute(query, args).fetchall()]
    finally:
        pg.close()


def _broadcast(task_id: str, event: str, data: Dict):
    with _lock:
        if task_id in _subscribers:
            for q in _subscribers[task_id]:
                try:
                    q.put_nowait({"event": event, "data": data})
                except Exception:
                    pass


def subscribe(task_id: str):
    import queue

    q = queue.Queue()
    with _lock:
        _subscribers.setdefault(task_id, []).append(q)
    try:
        while True:
            try:
                msg = q.get(timeout=30)
                yield msg["event"], msg["data"]
            except queue.Empty:
                yield "heartbeat", {}
    finally:
        with _lock:
            if task_id in _subscribers and q in _subscribers[task_id]:
                _subscribers[task_id].remove(q)
