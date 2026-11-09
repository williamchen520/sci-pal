"""PostgreSQL protocol runs (G3.10e2c)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from services.db.pg_pool import pg_connection
from services.db.tenant_pilot import set_search_path


def _pg():
    pg = pg_connection()
    set_search_path(pg, "protocols")
    return pg
from services.protocols.helpers import _done_steps, _now, _run_row, _run_status, _text


def add_run(
    protocol_id: str,
    *,
    title: str = "",
    operator: str = "",
    run_date: str = "",
    status: str = "planned",
    result: str = "",
    notes: str = "",
    done_steps: Any = None,
) -> Dict[str, Any]:
    status = _run_status(status)
    run_id = "run_" + uuid.uuid4().hex[:12]
    now = _now()
    steps_done = _done_steps(done_steps)
    row = {
        "run_id": run_id,
        "protocol_id": protocol_id,
        "title": _text(title),
        "operator": _text(operator),
        "run_date": _text(run_date) or now[:10],
        "status": status,
        "result": _text(result),
        "notes": _text(notes),
        "done_steps": json.dumps(steps_done, ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
    }
    pg = _pg()
    try:
        pg.execute(
            "INSERT INTO protocol_runs "
            "(run_id, protocol_id, title, operator, run_date, status, result, notes, "
            "done_steps, created_at, updated_at) "
            "VALUES (%(run_id)s, %(protocol_id)s, %(title)s, %(operator)s, %(run_date)s, "
            "%(status)s, %(result)s, %(notes)s, %(done_steps)s, %(created_at)s, %(updated_at)s)",
            row,
        )
        pg.commit()
    finally:
        pg.close()
    return {**row, "done_steps": steps_done}


def list_runs(protocol_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    pg = _pg()
    try:
        rows = pg.execute(
            "SELECT * FROM protocol_runs WHERE protocol_id = %s "
            "ORDER BY run_date DESC, created_at DESC LIMIT %s",
            (protocol_id, max(1, limit)),
        ).fetchall()
        return [_run_row(row) for row in rows]
    finally:
        pg.close()


def update_run(run_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    allowed = {"title", "operator", "run_date", "status", "result", "notes", "done_steps"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if "status" in updates:
        updates["status"] = _run_status(updates["status"])
    if "done_steps" in updates:
        updates["done_steps"] = json.dumps(_done_steps(updates["done_steps"]), ensure_ascii=False)
    if not updates:
        return None
    assignments = ", ".join(f"{key} = %s" for key in updates)
    pg = _pg()
    try:
        row = pg.execute(
            f"UPDATE protocol_runs SET {assignments}, updated_at = %s WHERE run_id = %s "
            "RETURNING *",
            [*updates.values(), _now(), run_id],
        ).fetchone()
        pg.commit()
        return _run_row(row) if row else None
    finally:
        pg.close()


def delete_run(run_id: str) -> bool:
    pg = _pg()
    try:
        row = pg.execute(
            "DELETE FROM protocol_runs WHERE run_id = %s RETURNING run_id", (run_id,)
        ).fetchone()
        pg.commit()
        return bool(row)
    finally:
        pg.close()

def recent_runs(limit: int = 20) -> List[Dict[str, Any]]:
    pg = _pg()
    try:
        rows = pg.execute(
            "SELECT r.*, p.title AS protocol_title FROM protocol_runs r "
            "LEFT JOIN protocol_imports p ON p.protocol_id = r.protocol_id "
            "ORDER BY r.run_date DESC, r.created_at DESC LIMIT %s",
            (max(1, limit),),
        ).fetchall()
        return [_run_row(row) for row in rows]
    finally:
        pg.close()
