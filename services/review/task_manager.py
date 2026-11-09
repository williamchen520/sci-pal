"""Review task constants/helpers and PostgreSQL task manager instance.

The SQLite TaskManager was retired with the PG-only migration. Call sites keep
importing ``task_manager``; the object is always PGTaskManager now.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

PERSISTED_TASK_TYPES = (
    "qa_ask",
    "agentic_search",
    "generate_outline",
    "generate_review",
    "parse_paper",
)

_SELECT_COLUMNS = (
    "task_id, type, status, progress_text, result, error, created_at, "
    "started_at, finished_at, progress_pct, params"
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_task(row) -> Dict[str, Any]:
    raw_result = row["result"]
    if raw_result is None:
        result: Any = None
    else:
        try:
            result = json.loads(raw_result)
        except (TypeError, ValueError):
            result = raw_result

    status = row["status"]
    return {
        "task_id": row["task_id"],
        "task_type": row["type"],
        "status": status,
        "progress": row["progress_text"] or "",
        "result": result,
        "error": row["error"],
        "cancelled": status == "cancelled",
    }


from .pg_tasks import PGTaskManager  # noqa: E402

task_manager = PGTaskManager()

try:
    task_manager.recover_stale_tasks()
except Exception:
    pass
