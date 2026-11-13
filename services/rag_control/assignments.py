"""R12: reviewer assignments and completion."""

from __future__ import annotations

import uuid
from typing import Any

from services.db.pg_pool import core_connection
from services.tenancy.service import get_membership

REVIEWER_ROLES = {"owner", "pi", "reviewer"}


class AssignmentError(ValueError):
    pass


def _assignment(row) -> dict[str, Any]:
    return {
        "assignment_id": row["assignment_id"],
        "multi_run_id": row["multi_run_id"],
        "rag_id": row["rag_id"],
        "reviewer_user_id": row["reviewer_user_id"],
        "status": row["status"],
        "assigned_by": row["assigned_by"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }


def list_assignments(multi_run_id: str) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM rag_review_assignments WHERE multi_run_id=%s ORDER BY rag_id,created_at",
            (multi_run_id,),
        ).fetchall()
        return [_assignment(row) for row in rows]
    finally:
        pg.close()


def assign(
    *, multi_run_id: str, rag_id: str, reviewer_user_id: str, assigned_by: str
) -> dict[str, Any]:
    if not rag_id or not reviewer_user_id:
        raise AssignmentError("rag_id and reviewer_user_id required")
    pg = core_connection()
    try:
        multi = pg.execute(
            "SELECT workspace_id FROM rag_multi_queries WHERE multi_run_id=%s", (multi_run_id,)
        ).fetchone()
        if not multi:
            raise AssignmentError("multi run not found")
        group = pg.execute(
            "SELECT 1 FROM rag_multi_groups WHERE multi_run_id=%s AND rag_id=%s",
            (multi_run_id, rag_id),
        ).fetchone()
        if not group:
            raise AssignmentError("rag group not found")
        membership = get_membership(multi["workspace_id"], reviewer_user_id)
        if not membership or membership.status != "active" or membership.role not in REVIEWER_ROLES:
            raise AssignmentError("target user is not an active reviewer")
        assignment_id = "asg_" + uuid.uuid4().hex[:12]
        pg.execute(
            """
            INSERT INTO rag_review_assignments
              (assignment_id,multi_run_id,rag_id,reviewer_user_id,assigned_by)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (multi_run_id,rag_id,reviewer_user_id) DO NOTHING
            """,
            (assignment_id, multi_run_id, rag_id, reviewer_user_id, assigned_by),
        )
        pg.commit()
        row = pg.execute(
            "SELECT * FROM rag_review_assignments WHERE multi_run_id=%s AND rag_id=%s AND reviewer_user_id=%s",
            (multi_run_id, rag_id, reviewer_user_id),
        ).fetchone()
        return _assignment(row)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def complete_assignment(*, multi_run_id: str, rag_id: str, reviewer_user_id: str) -> None:
    pg = core_connection()
    try:
        pg.execute(
            "UPDATE rag_review_assignments SET status='completed',completed_at=now() "
            "WHERE multi_run_id=%s AND rag_id=%s AND reviewer_user_id=%s AND status='assigned'",
            (multi_run_id, rag_id, reviewer_user_id),
        )
        pg.commit()
    finally:
        pg.close()
