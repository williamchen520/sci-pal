"""R13: human finalization gate and content seal hash."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from services.db.pg_pool import core_connection
from services.rag_control.adjudication import get_multi
from services.rag_control.agreement import agreement
from services.rag_control.assignments import list_assignments
from services.rag_control.signing import sign, verify

VALID_DECISIONS = {"accepted", "rejected", "needs_more_evidence"}


class FinalizationError(ValueError):
    pass


def canonical_json(run: dict[str, Any], agreement_data: dict[str, Any]) -> str:
    payload = {
        "multi_run_id": run["multi_run_id"],
        "query": run["query"],
        "rag_ids": run["rag_ids"],
        "groups": run["groups"],
        "adjudications": run["adjudications"],
        "conflicts": run["conflicts"],
        "agreement": agreement_data,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(run: dict[str, Any], agreement_data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(run, agreement_data).encode("utf-8")).hexdigest()


def finalize(
    *, multi_run_id: str, decision: str, note: str, finalized_by: str
) -> dict[str, Any]:
    if decision not in VALID_DECISIONS:
        raise FinalizationError("invalid decision")
    run = get_multi(multi_run_id)
    if not run:
        raise FinalizationError("multi run not found")
    if run.get("status") == "finalized":
        raise FinalizationError("already finalized")
    agreement_data = agreement(multi_run_id)
    if not agreement_data or agreement_data.get("reviewer_count", 0) < 2:
        raise FinalizationError("at least two reviewers are required")
    pending = [item for item in list_assignments(multi_run_id) if item["status"] != "completed"]
    if pending:
        raise FinalizationError("assigned reviewers are not complete")
    content_hash = _hash(run, agreement_data)
    seal = sign(content_hash)
    finalization_id = "fin_" + uuid.uuid4().hex[:12]
    pg = core_connection()
    try:
        pg.execute(
            "INSERT INTO rag_multi_finalizations "
            "(finalization_id,multi_run_id,decision,note,finalized_by,content_hash,"
            "signature,public_key,signature_algorithm,key_id,signed_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())",
            (
                finalization_id,
                multi_run_id,
                decision,
                note[:4000],
                finalized_by,
                content_hash,
                seal["signature"],
                seal["public_key"],
                seal["algorithm"],
                seal["key_id"],
            ),
        )
        pg.execute(
            "UPDATE rag_multi_queries SET status='finalized',finalized_by=%s,finalized_at=now() "
            "WHERE multi_run_id=%s",
            (finalized_by, multi_run_id),
        )
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
    return {
        "finalization_id": finalization_id,
        "multi_run_id": multi_run_id,
        "decision": decision,
        "note": note[:4000],
        "finalized_by": finalized_by,
        "content_hash": content_hash,
        "signature": seal["signature"],
        "public_key": seal["public_key"],
        "signature_algorithm": seal["algorithm"],
        "key_id": seal["key_id"],
        "signed_at": datetime.now(timezone.utc).isoformat(),
        "timestamp_source": "local_clock",
    }


def get_finalization(multi_run_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT * FROM rag_multi_finalizations WHERE multi_run_id=%s ORDER BY created_at DESC LIMIT 1",
            (multi_run_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "finalization_id": row["finalization_id"],
            "multi_run_id": row["multi_run_id"],
            "decision": row["decision"],
            "note": row["note"],
            "finalized_by": row["finalized_by"],
            "content_hash": row["content_hash"],
            "signature": row["signature"],
            "public_key": row["public_key"],
            "signature_algorithm": row["signature_algorithm"],
            "key_id": row["key_id"],
            "signed_at": row["signed_at"].isoformat() if row["signed_at"] else None,
            "timestamp_source": "local_clock",
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
    finally:
        pg.close()


def verify_seal(multi_run_id: str) -> dict[str, Any] | None:
    run = get_multi(multi_run_id)
    final = get_finalization(multi_run_id)
    if not run or not final:
        return None
    agreement_data = agreement(multi_run_id)
    expected = _hash(run, agreement_data) if agreement_data else ""
    return {
        "multi_run_id": multi_run_id,
        "content_hash_match": expected == final["content_hash"],
        "signature_valid": verify(
            final["content_hash"], final["signature"] or "", final["public_key"] or ""
        ),
        "key_id": final["key_id"],
        "signed_at": final["signed_at"],
        "timestamp_source": "local_clock",
    }
