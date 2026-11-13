"""R4: append-only evidence and artifact ledger."""

from __future__ import annotations

import json
import uuid
from typing import Any

from services.db.pg_pool import core_connection


class LedgerError(ValueError):
    pass


def _evidence(row) -> dict[str, Any]:
    return {
        "evidence_id": row["evidence_id"],
        "run_id": row["run_id"],
        "plan_id": row["plan_id"],
        "step_id": row["step_id"],
        "rag_id": row["rag_id"],
        "library_id": row["library_id"],
        "snapshot": row["snapshot"],
        "source_path": row["source_path"],
        "start_line": row["start_line"],
        "end_line": row["end_line"],
        "content_hash": row["content_hash"],
        "model_version": row["model_version"],
        "score": row["score"],
        "metadata": row["metadata"] or {},
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _artifact(row) -> dict[str, Any]:
    return {
        "artifact_id": row["artifact_id"],
        "run_id": row["run_id"],
        "kind": row["kind"],
        "uri": row["uri"],
        "sha256": row["sha256"],
        "size_bytes": row["size_bytes"],
        "license": row["license"],
        "metadata": row["metadata"] or {},
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


def _run_exists(pg, run_id: str) -> bool:
    return bool(pg.execute("SELECT 1 FROM rag_runs WHERE run_id=%s", (run_id,)).fetchone())


def append_evidence(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    pg = core_connection()
    try:
        if not _run_exists(pg, run_id):
            raise LedgerError("run not found")
        evidence_id = "ev_" + uuid.uuid4().hex[:12]
        pg.execute(
            """
            INSERT INTO rag_evidence
              (evidence_id,run_id,plan_id,step_id,rag_id,library_id,snapshot,
               source_path,start_line,end_line,content_hash,model_version,score,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                evidence_id,
                run_id,
                str(payload.get("plan_id") or ""),
                str(payload.get("step_id") or ""),
                str(payload.get("rag_id") or ""),
                str(payload.get("library_id") or ""),
                str(payload.get("snapshot") or ""),
                str(payload.get("source_path") or ""),
                payload.get("start_line"),
                payload.get("end_line"),
                str(payload.get("content_hash") or ""),
                str(payload.get("model_version") or ""),
                payload.get("score"),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
            ),
        )
        pg.commit()
        row = pg.execute("SELECT * FROM rag_evidence WHERE evidence_id=%s", (evidence_id,)).fetchone()
        return _evidence(row)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def list_evidence(run_id: str) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM rag_evidence WHERE run_id=%s ORDER BY created_at,evidence_id", (run_id,)
        ).fetchall()
        return [_evidence(row) for row in rows]
    finally:
        pg.close()


def append_artifact(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    kind = str(payload.get("kind") or "").strip()
    uri = str(payload.get("uri") or "").strip()
    if not kind or not uri:
        raise LedgerError("kind and uri required")
    pg = core_connection()
    try:
        if not _run_exists(pg, run_id):
            raise LedgerError("run not found")
        artifact_id = "art_" + uuid.uuid4().hex[:12]
        pg.execute(
            """
            INSERT INTO rag_artifacts
              (artifact_id,run_id,kind,uri,sha256,size_bytes,license,metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                artifact_id,
                run_id,
                kind,
                uri,
                str(payload.get("sha256") or ""),
                payload.get("size_bytes"),
                str(payload.get("license") or ""),
                json.dumps(payload.get("metadata") or {}, ensure_ascii=False),
            ),
        )
        pg.commit()
        row = pg.execute("SELECT * FROM rag_artifacts WHERE artifact_id=%s", (artifact_id,)).fetchone()
        return _artifact(row)
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()


def list_artifacts(run_id: str) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM rag_artifacts WHERE run_id=%s ORDER BY created_at,artifact_id", (run_id,)
        ).fetchall()
        return [_artifact(row) for row in rows]
    finally:
        pg.close()
