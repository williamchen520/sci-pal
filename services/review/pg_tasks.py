"""PostgreSQL review TaskManager (G3.10f1)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from services.db.pg_pool import pg_connection
from services.db.tenant_pilot import set_search_path


def _pg():
    pg = pg_connection()
    set_search_path(pg, "systematic")
    return pg
from services.review.task_manager import (
    PERSISTED_TASK_TYPES,
    _SELECT_COLUMNS,
    _now,
    _row_to_task,
)


class PGTaskManager:
    def create_task(self, task_type: str, params: Optional[dict] = None) -> str:
        task_id = str(uuid.uuid4())
        now = _now()
        params_text = None
        if params is not None:
            try:
                params_text = json.dumps(params, ensure_ascii=False)
            except (TypeError, ValueError):
                params_text = json.dumps(str(params), ensure_ascii=False)
        pg = _pg()
        try:
            pg.execute(
                "INSERT INTO tasks (task_id, type, status, progress_text, result, error, "
                "created_at, started_at, progress_pct, params) "
                "VALUES (%s, %s, 'queued', '排队中...', NULL, NULL, %s, NULL, 0, %s)",
                (task_id, task_type, now, params_text),
            )
            pg.commit()
        finally:
            pg.close()
        return task_id

    def claim_task(self, task_id: str) -> bool:
        pg = _pg()
        try:
            row = pg.execute(
                "UPDATE tasks SET status='running', started_at=%s, progress_text='初始化中...' "
                "WHERE task_id=%s AND status='queued' RETURNING task_id",
                (_now(), task_id),
            ).fetchone()
            pg.commit()
            return bool(row)
        finally:
            pg.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        pg = _pg()
        try:
            row = pg.execute(
                f"SELECT {_SELECT_COLUMNS} FROM tasks WHERE task_id = %s", (task_id,)
            ).fetchone()
            return _row_to_task(row) if row else None
        finally:
            pg.close()

    def cancel_task(self, task_id: str) -> bool:
        pg = _pg()
        try:
            row = pg.execute(
                "UPDATE tasks SET status='cancelled', finished_at=%s "
                "WHERE task_id = %s AND status IN ('queued','running') RETURNING task_id",
                (_now(), task_id),
            ).fetchone()
            pg.commit()
            return bool(row)
        finally:
            pg.close()

    def complete_task(self, task_id: str, result: Any) -> bool:
        payload = None if result is None else json.dumps(result, ensure_ascii=False)
        pg = _pg()
        try:
            row = pg.execute(
                "UPDATE tasks SET status='completed', result=%s, progress_pct=100, finished_at=%s "
                "WHERE task_id = %s AND status = 'running' RETURNING task_id",
                (payload, _now(), task_id),
            ).fetchone()
            pg.commit()
            return bool(row)
        finally:
            pg.close()

    def fail_task(self, task_id: str, error: str) -> bool:
        pg = _pg()
        try:
            row = pg.execute(
                "UPDATE tasks SET status='failed', error=%s, finished_at=%s "
                "WHERE task_id = %s AND status = 'running' RETURNING task_id",
                (error, _now(), task_id),
            ).fetchone()
            pg.commit()
            return bool(row)
        finally:
            pg.close()

    def is_cancelled(self, task_id: str) -> bool:
        pg = _pg()
        try:
            row = pg.execute(
                "SELECT status FROM tasks WHERE task_id = %s", (task_id,)
            ).fetchone()
            return bool(row and row["status"] == "cancelled")
        finally:
            pg.close()

    def update_progress(self, task_id: str, progress: str) -> None:
        pg = _pg()
        try:
            pg.execute(
                "UPDATE tasks SET progress_text=%s WHERE task_id = %s AND status = 'running'",
                (progress, task_id),
            )
            pg.commit()
        finally:
            pg.close()

    def get_running_task(self) -> Optional[Dict[str, Any]]:
        placeholders = ",".join("%s" for _ in PERSISTED_TASK_TYPES)
        pg = _pg()
        try:
            row = pg.execute(
                f"SELECT {_SELECT_COLUMNS} FROM tasks "
                f"WHERE status IN ('queued','running') AND type IN ({placeholders}) "
                "ORDER BY created_at ASC LIMIT 1",
                PERSISTED_TASK_TYPES,
            ).fetchone()
            return _row_to_task(row) if row else None
        finally:
            pg.close()

    def recover_stale_tasks(self, max_age_minutes: int = 120) -> int:
        from datetime import datetime, timedelta

        cutoff = (datetime.now() - timedelta(minutes=max_age_minutes)).isoformat(timespec="seconds")
        pg = _pg()
        try:
            rows = pg.execute(
                "UPDATE tasks SET status='failed', error='stale task recovery', finished_at=%s "
                "WHERE status IN ('queued','running') AND created_at < %s RETURNING task_id",
                (_now(), cutoff),
            ).fetchall()
            pg.commit()
            return len(rows)
        finally:
            pg.close()

    def cleanup_old_tasks(self, max_count: int = 100) -> None:
        placeholders = ",".join("%s" for _ in PERSISTED_TASK_TYPES)
        pg = _pg()
        try:
            total = pg.execute(
                f"SELECT COUNT(*) AS n FROM tasks WHERE type IN ({placeholders})",
                PERSISTED_TASK_TYPES,
            ).fetchone()["n"]
            if total <= max_count:
                return
            pg.execute(
                "DELETE FROM tasks WHERE task_id IN ("
                f"  SELECT task_id FROM tasks WHERE type IN ({placeholders}) "
                "  ORDER BY created_at ASC LIMIT %s"
                ")",
                (*PERSISTED_TASK_TYPES, total - max_count),
            )
            pg.commit()
        finally:
            pg.close()
