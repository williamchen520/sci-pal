"""R7: grouped evidence view and human adjudication."""

from __future__ import annotations

import uuid
from typing import Any

from services.db.pg_pool import core_connection
from services.rag_control.ledger import list_evidence

VALID_DECISIONS = {"accept", "reject", "needs_more_evidence"}


class AdjudicationError(ValueError):
    pass


def _multi(row) -> dict[str, Any]:
    return {
        "multi_run_id": row["multi_run_id"],
        "query": row["query"],
        "rag_ids": row["rag_ids"] or [],
        "library_id": row["library_id"],
        "workspace_id": row["workspace_id"],
        "status": row["status"],
        "finalized_by": row["finalized_by"],
        "finalized_at": row["finalized_at"].isoformat() if row["finalized_at"] else None,
        "created_by": row["created_by"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def list_multi(limit: int = 20) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM rag_multi_queries ORDER BY created_at DESC LIMIT %s",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [_multi(row) for row in rows]
    finally:
        pg.close()


def get_multi(multi_run_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT * FROM rag_multi_queries WHERE multi_run_id=%s", (multi_run_id,)
        ).fetchone()
        if not row:
            return None
        groups = pg.execute(
            "SELECT * FROM rag_multi_groups WHERE multi_run_id=%s ORDER BY rag_id", (multi_run_id,)
        ).fetchall()
        decisions = pg.execute(
            "SELECT * FROM rag_adjudications WHERE multi_run_id=%s ORDER BY created_at", (multi_run_id,)
        ).fetchall()
        conflicts = pg.execute(
            "SELECT * FROM rag_conflict_flags WHERE multi_run_id=%s ORDER BY created_at", (multi_run_id,)
        ).fetchall()
    finally:
        pg.close()
    result = _multi(row)
    result["groups"] = [
        {
            "rag_id": group["rag_id"],
            "run_id": group["run_id"],
            "status": group["status"],
            "result_count": group["result_count"],
            "machine_signal": group["machine_signal"],
            "evidence": list_evidence(group["run_id"]) if group["run_id"] else [],
        }
        for group in groups
    ]
    seen: dict[str, str] = {}
    duplicates = 0
    for group in result["groups"]:
        for item in group["evidence"]:
            key = item.get("content_hash") or f"{item.get('source_path')}:{item.get('start_line')}:{item.get('end_line')}"
            if key in seen:
                item["duplicate_of"] = seen[key]
                duplicates += 1
            else:
                seen[key] = item["evidence_id"]
    result["duplicate_count"] = duplicates
    result["conflicts"] = [
        {
            "flag_id": item["flag_id"],
            "rag_id": item["rag_id"],
            "note": item["note"],
            "flagged_by": item["flagged_by"],
            "created_at": item["created_at"].isoformat() if item["created_at"] else None,
        }
        for item in conflicts
    ]
    result["adjudications"] = [
        {
            "adjudication_id": item["adjudication_id"],
            "rag_id": item["rag_id"],
            "decision": item["decision"],
            "note": item["note"],
            "decided_by": item["decided_by"],
            "created_at": item["created_at"].isoformat() if item["created_at"] else None,
        }
        for item in decisions
    ]
    return result


def add_adjudication(
    *, multi_run_id: str, rag_id: str, decision: str, note: str, decided_by: str
) -> dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise AdjudicationError("invalid decision")
    if not rag_id:
        raise AdjudicationError("rag_id required")
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT status FROM rag_multi_queries WHERE multi_run_id=%s", (multi_run_id,)
        ).fetchone()
        if not row:
            raise AdjudicationError("multi run not found")
        if row["status"] == "finalized":
            raise AdjudicationError("multi run finalized")
        if rag_id != "*":
            group = pg.execute(
                "SELECT 1 FROM rag_multi_groups WHERE multi_run_id=%s AND rag_id=%s",
                (multi_run_id, rag_id),
            ).fetchone()
            if not group:
                raise AdjudicationError("rag group not found")
        adjudication_id = "adj_" + uuid.uuid4().hex[:12]
        pg.execute(
            "INSERT INTO rag_adjudications (adjudication_id,multi_run_id,rag_id,decision,note,decided_by) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (adjudication_id, multi_run_id, rag_id, decision, note[:4000], decided_by),
        )
        pg.commit()
        return {
            "adjudication_id": adjudication_id,
            "multi_run_id": multi_run_id,
            "rag_id": rag_id,
            "decision": decision,
            "note": note[:4000],
            "decided_by": decided_by,
        }
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def add_conflict(*, multi_run_id: str, rag_id: str, note: str, flagged_by: str) -> dict[str, Any]:
    if not rag_id:
        raise AdjudicationError("rag_id required")
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT status FROM rag_multi_queries WHERE multi_run_id=%s", (multi_run_id,)
        ).fetchone()
        if not row:
            raise AdjudicationError("multi run not found")
        if row["status"] == "finalized":
            raise AdjudicationError("multi run finalized")
        group = pg.execute(
            "SELECT 1 FROM rag_multi_groups WHERE multi_run_id=%s AND rag_id=%s",
            (multi_run_id, rag_id),
        ).fetchone()
        if not group:
            raise AdjudicationError("rag group not found")
        flag_id = "cf_" + uuid.uuid4().hex[:12]
        pg.execute(
            "INSERT INTO rag_conflict_flags (flag_id,multi_run_id,rag_id,note,flagged_by) "
            "VALUES (%s,%s,%s,%s,%s)",
            (flag_id, multi_run_id, rag_id, note[:4000], flagged_by),
        )
        pg.commit()
        return {"flag_id": flag_id, "multi_run_id": multi_run_id, "rag_id": rag_id, "note": note[:4000], "flagged_by": flagged_by}
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
