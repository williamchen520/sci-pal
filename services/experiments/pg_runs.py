"""PostgreSQL backend for experiment_runs (G3.10c)."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, List, Optional

from services.db.pg_pool import pg_connection
from services.experiments import pg_read

RUN_STATUSES = ("planned", "running", "completed", "failed", "abandoned")


def enabled() -> bool:
    return os.environ.get("SCIPAL_RUNS_BACKEND", "").strip().lower() in {
        "postgres", "postgresql", "pg", "1", "true"
    }


def list_runs(experiment_id: str, workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    if not pg_read.get_experiment(experiment_id, workspace_id, user_id):
        return None
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM experiment_runs WHERE experiment_id = %s AND workspace_id = %s "
            "AND owner_user_id = %s ORDER BY created_at, run_id",
            (experiment_id, workspace_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def create_run(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    title: str,
    *,
    status: str = "planned",
    planned: Optional[dict] = None,
    actual: Optional[dict] = None,
    observations: str = "",
    result: str = "",
) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if status not in RUN_STATUSES:
        raise ValueError("invalid status")
    experiment = pg_read.get_experiment(experiment_id, workspace_id, user_id)
    if not experiment or experiment["owner_user_id"] != user_id:
        raise PermissionError("experiment access denied")
    run_id = f"run_{uuid.uuid4().hex}"
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO experiment_runs "
            "(run_id, experiment_id, workspace_id, owner_user_id, protocol_id, title, status, "
            "planned_json, actual_json, observations, result, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())",
            (
                run_id, experiment_id, workspace_id, user_id, experiment.get("protocol_id"),
                title, status, json.dumps(planned or {}, ensure_ascii=False),
                json.dumps(actual or {}, ensure_ascii=False), observations, result,
            ),
        )
        pg.commit()
        row = pg.execute(
            "SELECT * FROM experiment_runs WHERE run_id = %s", (run_id,)
        ).fetchone()
        return dict(row)
    finally:
        pg.close()


def get_run(run_id: str, workspace_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    pg = pg_connection()
    try:
        row = pg.execute(
            "SELECT * FROM experiment_runs WHERE run_id = %s AND workspace_id = %s "
            "AND owner_user_id = %s",
            (run_id, workspace_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        pg.close()


def update_run(
    run_id: str,
    workspace_id: str,
    user_id: str,
    *,
    title: Optional[str] = None,
    status: Optional[str] = None,
    planned: Optional[dict] = None,
    actual: Optional[dict] = None,
    observations: Optional[str] = None,
    result: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    fields = {}
    if title is not None:
        if not title.strip():
            raise ValueError("title is required")
        fields["title"] = title.strip()
    if status is not None:
        if status not in RUN_STATUSES:
            raise ValueError("invalid status")
        fields["status"] = status
    if planned is not None:
        fields["planned_json"] = json.dumps(planned, ensure_ascii=False)
    if actual is not None:
        fields["actual_json"] = json.dumps(actual, ensure_ascii=False)
    if observations is not None:
        fields["observations"] = observations
    if result is not None:
        fields["result"] = result
    if fields:
        assignments = ", ".join(f"{key} = %s" for key in fields)
        pg = pg_connection()
        try:
            row = pg.execute(
                f"UPDATE experiment_runs SET {assignments}, updated_at = now() "
                "WHERE run_id = %s AND workspace_id = %s AND owner_user_id = %s "
                "RETURNING run_id",
                [*fields.values(), run_id, workspace_id, user_id],
            ).fetchone()
            pg.commit()
            if not row:
                return None
        finally:
            pg.close()
    return get_run(run_id, workspace_id, user_id)
