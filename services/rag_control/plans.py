"""R1: RAG plans, approvals, jobs, runs, and worker leases."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from services.db.pg_pool import core_connection
from services.rag_control.registry import get_provider

VALID_ACTIONS = {"rag_query", "rag_ingest", "reindex", "eval"}
VALID_RISK = {"low", "medium", "high"}


class PlanError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _plan_hash(intent: str, steps: list[dict[str, Any]]) -> str:
    payload = {"intent": intent, "steps": steps}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _step(row) -> dict[str, Any]:
    return {
        "step_id": row["step_id"],
        "step_order": row["step_order"],
        "action": row["action"],
        "rag_id": row["rag_id"],
        "library_id": row["library_id"],
        "query": row["query"],
        "snapshot": row["snapshot"],
        "depends_on": row["depends_on"] or [],
        "status": row["status"],
        "risk_level": row["risk_level"],
        "timeout_seconds": row["timeout_seconds"],
        "params": row["params"] or {},
    }


def _plan(row, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "plan_id": row["plan_id"],
        "intent": row["intent"],
        "status": row["status"],
        "risk_level": row["risk_level"],
        "plan_hash": row["plan_hash"],
        "created_by": row["created_by"],
        "approved_by": row["approved_by"],
        "approved_at": _iso(row["approved_at"]),
        "expires_at": _iso(row["expires_at"]),
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
        "steps": steps,
    }


def _read_plan(pg, plan_id: str) -> dict[str, Any] | None:
    row = pg.execute("SELECT * FROM rag_plans WHERE plan_id=%s", (plan_id,)).fetchone()
    if not row:
        return None
    steps = pg.execute(
        "SELECT * FROM rag_plan_steps WHERE plan_id=%s ORDER BY step_order", (plan_id,)
    ).fetchall()
    return _plan(row, [_step(item) for item in steps])


def get_plan(plan_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        return _read_plan(pg, plan_id)
    finally:
        pg.close()


def create_plan(*, intent: str, steps: list[dict[str, Any]], created_by: str) -> dict[str, Any]:
    intent = (intent or "").strip()
    if not intent:
        raise PlanError("intent required")
    if not isinstance(steps, list) or not steps or len(steps) > 20:
        raise PlanError("steps must contain 1-20 items")
    clean = []
    risk = "low"
    for index, step in enumerate(steps, 1):
        action = str(step.get("action") or "").strip()
        rag_id = str(step.get("rag_id") or "").strip()
        if action not in VALID_ACTIONS:
            raise PlanError(f"invalid action: {action}")
        if not rag_id:
            raise PlanError("rag_id required")
        provider = get_provider(rag_id)
        if not provider:
            raise PlanError(f"unknown rag: {rag_id}")
        step_risk = "high" if action in {"rag_ingest", "reindex"} else "low"
        if step.get("risk_level") in VALID_RISK:
            step_risk = step["risk_level"]
        risk = max(risk, step_risk, key=["low", "medium", "high"].index)
        clean.append(
            {
                "action": action,
                "rag_id": rag_id,
                "library_id": str(step.get("library_id") or ""),
                "query": str(step.get("query") or ""),
                "snapshot": str(step.get("snapshot") or ""),
                "depends_on": list(step.get("depends_on") or []),
                "risk_level": step_risk,
                "timeout_seconds": max(1, min(int(step.get("timeout_seconds") or 300), 86400)),
                "params": dict(step.get("params") or {}),
            }
        )
    plan_id = "plan_" + uuid.uuid4().hex[:12]
    digest = _plan_hash(intent, clean)
    pg = core_connection()
    try:
        pg.execute(
            """
            INSERT INTO rag_plans (plan_id,intent,status,risk_level,plan_hash,created_by,payload)
            VALUES (%s,%s,'proposed',%s,%s,%s,%s::jsonb)
            """,
            (plan_id, intent, risk, digest, created_by, json.dumps({"steps": clean}, ensure_ascii=False)),
        )
        for order, step in enumerate(clean, 1):
            pg.execute(
                """
                INSERT INTO rag_plan_steps
                  (step_id,plan_id,step_order,action,rag_id,library_id,query,snapshot,
                   depends_on,status,risk_level,timeout_seconds,params)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'proposed',%s,%s,%s::jsonb)
                """,
                (
                    "step_" + uuid.uuid4().hex[:12],
                    plan_id,
                    order,
                    step["action"],
                    step["rag_id"],
                    step["library_id"],
                    step["query"],
                    step["snapshot"],
                    json.dumps(step["depends_on"]),
                    step["risk_level"],
                    step["timeout_seconds"],
                    json.dumps(step["params"], ensure_ascii=False),
                ),
            )
        pg.commit()
        return _read_plan(pg, plan_id)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def approve_plan(*, plan_id: str, approved_by: str, plan_hash: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute("SELECT * FROM rag_plans WHERE plan_id=%s FOR UPDATE", (plan_id,)).fetchone()
        if not row:
            return None
        if row["status"] != "proposed":
            raise PlanError(f"plan is {row['status']}")
        if plan_hash != row["plan_hash"]:
            raise PlanError("plan hash mismatch")
        pg.execute(
            "UPDATE rag_plans SET status='approved',approved_by=%s,approved_at=now(),"
            "expires_at=now()+interval '1 hour',updated_at=now() WHERE plan_id=%s",
            (approved_by, plan_id),
        )
        pg.commit()
        return _read_plan(pg, plan_id)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def dispatch_plan(*, plan_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute("SELECT * FROM rag_plans WHERE plan_id=%s FOR UPDATE", (plan_id,)).fetchone()
        if not row:
            return None
        if row["status"] != "approved":
            raise PlanError(f"plan is {row['status']}")
        if row["expires_at"] and row["expires_at"] < _now():
            raise PlanError("approval expired")
        steps = pg.execute(
            "SELECT * FROM rag_plan_steps WHERE plan_id=%s ORDER BY step_order", (plan_id,)
        ).fetchall()
        for step in steps:
            pg.execute(
                """
                INSERT INTO rag_jobs
                  (job_id,plan_id,step_id,rag_id,library_id,job_type,status,payload)
                VALUES (%s,%s,%s,%s,%s,%s,'queued',%s::jsonb)
                """,
                (
                    "job_" + uuid.uuid4().hex[:12],
                    plan_id,
                    step["step_id"],
                    step["rag_id"],
                    step["library_id"],
                    step["action"],
                    json.dumps(
                        {
                            "query": step["query"],
                            "snapshot": step["snapshot"],
                            "timeout_seconds": step["timeout_seconds"],
                            "params": step["params"] or {},
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            pg.execute("UPDATE rag_plan_steps SET status='queued' WHERE step_id=%s", (step["step_id"],))
        pg.execute("UPDATE rag_plans SET status='dispatched',updated_at=now() WHERE plan_id=%s", (plan_id,))
        pg.commit()
        return _read_plan(pg, plan_id)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def lease_job(*, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute(
            """
            SELECT * FROM rag_jobs
            WHERE status='queued'
            ORDER BY priority DESC, created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """
        ).fetchone()
        if not row:
            pg.commit()
            return None
        pg.execute(
            "UPDATE rag_jobs SET status='leased',lease_owner=%s,lease_expires_at=now()+%s*interval '1 second',"
            "attempts=attempts+1,started_at=COALESCE(started_at,now()) WHERE job_id=%s",
            (worker_id, max(10, min(int(lease_seconds), 300)), row["job_id"]),
        )
        pg.commit()
        fresh = pg.execute("SELECT * FROM rag_jobs WHERE job_id=%s", (row["job_id"],)).fetchone()
        return _job(fresh)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def heartbeat(*, job_id: str, worker_id: str, lease_seconds: int = 60) -> bool:
    pg = core_connection()
    try:
        row = pg.execute(
            "UPDATE rag_jobs SET lease_expires_at=now()+%s*interval '1 second' "
            "WHERE job_id=%s AND lease_owner=%s AND status IN ('leased','running') RETURNING job_id",
            (max(10, min(int(lease_seconds), 300)), job_id, worker_id),
        ).fetchone()
        pg.commit()
        return bool(row)
    finally:
        pg.close()


def complete_job(*, job_id: str, worker_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        job = pg.execute(
            "SELECT * FROM rag_jobs WHERE job_id=%s FOR UPDATE", (job_id,)
        ).fetchone()
        if not job or job["lease_owner"] != worker_id:
            return None
        run_id = "run_" + uuid.uuid4().hex[:12]
        pg.execute(
            """
            INSERT INTO rag_runs
              (run_id,job_id,rag_id,library_id,snapshot,model_version,env_hash,exit_code,artifact_uri,metrics,started_at,finished_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,now())
            """,
            (
                run_id,
                job_id,
                job["rag_id"],
                job["library_id"],
                str(payload.get("snapshot") or ""),
                str(payload.get("model_version") or ""),
                str(payload.get("env_hash") or ""),
                payload.get("exit_code"),
                str(payload.get("artifact_uri") or ""),
                json.dumps(payload.get("metrics") or {}),
                job["started_at"],
            ),
        )
        pg.execute(
            "UPDATE rag_jobs SET status='succeeded',finished_at=now(),lease_expires_at=NULL WHERE job_id=%s",
            (job_id,),
        )
        pg.execute("UPDATE rag_plan_steps SET status='succeeded' WHERE step_id=%s", (job["step_id"],))
        remaining = pg.execute(
            "SELECT count(*) AS n FROM rag_plan_steps WHERE plan_id=%s AND status NOT IN ('succeeded','cancelled')",
            (job["plan_id"],),
        ).fetchone()["n"]
        if remaining == 0:
            pg.execute("UPDATE rag_plans SET status='succeeded',updated_at=now() WHERE plan_id=%s", (job["plan_id"],))
        pg.commit()
        return {"job_id": job_id, "run_id": run_id, "status": "succeeded"}
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def fail_job(*, job_id: str, worker_id: str, error: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        job = pg.execute("SELECT * FROM rag_jobs WHERE job_id=%s FOR UPDATE", (job_id,)).fetchone()
        if not job or job["lease_owner"] != worker_id:
            return None
        retry = job["attempts"] < job["max_attempts"]
        status = "queued" if retry else "failed"
        pg.execute(
            "UPDATE rag_jobs SET status=%s,error=%s,lease_owner=NULL,lease_expires_at=NULL,"
            "finished_at=CASE WHEN %s='failed' THEN now() ELSE NULL END WHERE job_id=%s",
            (status, error[:2000], status, job_id),
        )
        if not retry:
            pg.execute("UPDATE rag_plan_steps SET status='failed' WHERE step_id=%s", (job["step_id"],))
            pg.execute("UPDATE rag_plans SET status='failed',updated_at=now() WHERE plan_id=%s", (job["plan_id"],))
        pg.commit()
        return {"job_id": job_id, "status": status}
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def _job(row) -> dict[str, Any]:
    return {
        "job_id": row["job_id"],
        "plan_id": row["plan_id"],
        "step_id": row["step_id"],
        "rag_id": row["rag_id"],
        "library_id": row["library_id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "payload": row["payload"] or {},
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "lease_expires_at": _iso(row["lease_expires_at"]),
        "error": row["error"],
    }


def get_job(job_id: str) -> dict[str, Any] | None:
    pg = core_connection()
    try:
        row = pg.execute("SELECT * FROM rag_jobs WHERE job_id=%s", (job_id,)).fetchone()
        return _job(row) if row else None
    finally:
        pg.close()


def cancel_plan(plan_id: str) -> bool:
    pg = core_connection()
    try:
        row = pg.execute(
            "UPDATE rag_plans SET status='cancelled',updated_at=now() "
            "WHERE plan_id=%s AND status IN ('proposed','approved','dispatched','running') RETURNING plan_id",
            (plan_id,),
        ).fetchone()
        pg.execute(
            "UPDATE rag_jobs SET status='cancelled' WHERE plan_id=%s AND status IN ('queued','leased','running')",
            (plan_id,),
        )
        pg.execute("UPDATE rag_plan_steps SET status='cancelled' WHERE plan_id=%s AND status <> 'succeeded'", (plan_id,))
        pg.commit()
        return bool(row)
    finally:
        pg.close()
