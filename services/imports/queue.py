"""U1: durable import queue claiming and worker execution."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import core_connection
from services.imports import session
from services.imports.code_lane import CodeLaneAdapter
from services.imports.orchestrator import process_import
from services.imports.paper_lane import PaperLaneAdapter


class QueueError(ValueError):
    pass


def claim_next(import_id: str | None = None) -> str | None:
    with core_connection() as pg:
        if import_id:
            row = pg.execute(
                "UPDATE import_sessions SET status='running', updated_at=now() "
                "WHERE import_id=%s AND status='queued' RETURNING import_id",
                (import_id,),
            ).fetchone()
        else:
            row = pg.execute(
                """
                WITH next AS (
                    SELECT import_id FROM import_sessions
                    WHERE status='queued'
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE import_sessions s
                SET status='running', updated_at=now()
                FROM next
                WHERE s.import_id = next.import_id
                RETURNING s.import_id
                """
            ).fetchone()
    return row["import_id"] if row else None


def run_once(import_id: str | None = None) -> dict[str, Any] | None:
    claimed = claim_next(import_id)
    if not claimed:
        return None
    try:
        return process_import(
            claimed,
            paper_adapter=PaperLaneAdapter(build=True),
            code_adapter=CodeLaneAdapter(build=True),
        )
    except Exception as exc:  # noqa: BLE001
        session.finalize_session(claimed, processed=0, failed=1, status="failed")
        return {"import_id": claimed, "status": "failed", "error": str(exc)[:500]}


def requeue(import_id: str) -> dict[str, Any]:
    with core_connection() as pg:
        row = pg.execute(
            "UPDATE import_sessions SET status='queued', updated_at=now() "
            "WHERE import_id=%s AND status IN ('failed','partial','queued') "
            "RETURNING import_id,status",
            (import_id,),
        ).fetchone()
    if not row:
        raise QueueError("import is not requeueable")
    return dict(row)
