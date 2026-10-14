"""
V33.12 - 统一任务管理器
把综述任务和下载任务的状态统一写入 SQLite tasks 表。
重启不丢失，前端可查询历史。
"""

import sqlite3
import json
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Database path (same as main DB)
DB_PATH = Path("data/research.db")

# In-memory event subscribers for SSE
_subscribers: Dict[str, List] = {}  # task_id -> list of queue.Queue
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def create_task(task_type: str, params: Optional[Dict] = None, task_id: Optional[str] = None) -> str:
    """Create a new task record. Returns task_id. If task_id provided, use it."""
    if task_id is None:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
    now = datetime.now().isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO tasks (task_id, type, status, progress_text, progress_pct, params, created_at, started_at) VALUES (?, ?, 'running', '初始化中...', 0, ?, ?, ?)",
            (task_id, task_type, json.dumps(params or {}, ensure_ascii=False), now, now)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # task_id already exists, skip
    finally:
        conn.close()
    _broadcast(task_id, "created", {"task_id": task_id, "type": task_type})
    return task_id


def update_progress(task_id: str, text: str, pct: float = 0):
    """Update task progress."""
    conn = _get_conn()
    conn.execute(
        "UPDATE tasks SET progress_text = ?, progress_pct = ? WHERE task_id = ? AND status = 'running'",
        (text, pct, task_id)
    )
    conn.commit()
    conn.close()
    _broadcast(task_id, "progress", {"text": text, "pct": pct})


def complete_task(task_id: str, result: Any = None):
    """Mark task as completed."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute(
        "UPDATE tasks SET status = 'completed', progress_pct = 100, finished_at = ?, result = ? WHERE task_id = ?",
        (now, json.dumps(result, ensure_ascii=False) if result else None, task_id)
    )
    conn.commit()
    conn.close()
    _broadcast(task_id, "done", {"status": "completed"})


def fail_task(task_id: str, error: str):
    """Mark task as failed."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute(
        "UPDATE tasks SET status = 'failed', finished_at = ?, error = ? WHERE task_id = ?",
        (now, error, task_id)
    )
    conn.commit()
    conn.close()
    _broadcast(task_id, "error", {"error": error})


def cancel_task(task_id: str):
    """Mark task as cancelled."""
    now = datetime.now().isoformat()
    conn = _get_conn()
    conn.execute(
        "UPDATE tasks SET status = 'cancelled', finished_at = ? WHERE task_id = ?",
        (now, task_id)
    )
    conn.commit()
    conn.close()
    _broadcast(task_id, "cancelled", {"status": "cancelled"})


def get_task(task_id: str) -> Optional[Dict]:
    """Get task by ID."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_tasks(task_type: Optional[str] = None, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """List tasks with optional filters."""
    conn = _get_conn()
    query = "SELECT * FROM tasks WHERE 1=1"
    args = []
    if task_type:
        query += " AND type = ?"
        args.append(task_type)
    if status:
        query += " AND status = ?"
        args.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit)
    rows = conn.execute(query, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _broadcast(task_id: str, event: str, data: Dict):
    """Broadcast an event to all SSE subscribers for this task."""
    with _lock:
        if task_id in _subscribers:
            for q in _subscribers[task_id]:
                try:
                    q.put_nowait({"event": event, "data": data})
                except:
                    pass


def subscribe(task_id: str):
    """Generator for SSE events. Yields (event, data) tuples."""
    import queue
    q = queue.Queue()
    with _lock:
        if task_id not in _subscribers:
            _subscribers[task_id] = []
        _subscribers[task_id].append(q)
    try:
        while True:
            try:
                msg = q.get(timeout=30)
                yield msg["event"], msg["data"]
            except queue.Empty:
                # Keep-alive heartbeat
                yield "heartbeat", {}
    finally:
        with _lock:
            if task_id in _subscribers and q in _subscribers[task_id]:
                _subscribers[task_id].remove(q)
