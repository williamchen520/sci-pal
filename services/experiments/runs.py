"""Experiment runs: two-level experiment/run records."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from config.settings import DATABASE_PATH
from services.experiments.service import get_experiment
from services.experiments.service import ensure_experiments_schema


RUN_STATUSES = ("planned", "running", "completed", "failed", "abandoned")

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS experiment_runs (
        run_id TEXT PRIMARY KEY,
        experiment_id TEXT,
        workspace_id TEXT,
        owner_user_id TEXT,
        protocol_id TEXT,
        title TEXT,
        operator TEXT,
        run_date TEXT,
        status TEXT NOT NULL DEFAULT 'planned',
        planned_json TEXT DEFAULT '{}',
        actual_json TEXT DEFAULT '{}',
        observations TEXT DEFAULT '',
        result TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        started_at TEXT,
        ended_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_exp_runs_experiment ON experiment_runs(experiment_id)",
)


def ensure_runs_schema(conn: sqlite3.Connection) -> None:
    ensure_experiments_schema(conn)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "experiment_runs" not in tables:
        for statement in SCHEMA:
            conn.execute(statement)
    else:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(experiment_runs)")}
        for name, definition in {
            "experiment_id": "TEXT",
            "workspace_id": "TEXT",
            "owner_user_id": "TEXT",
            "planned_json": "TEXT DEFAULT '{}'",
            "actual_json": "TEXT DEFAULT '{}'",
            "observations": "TEXT DEFAULT ''",
            "started_at": "TEXT",
            "ended_at": "TEXT",
        }.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE experiment_runs ADD COLUMN {name} {definition}")
    conn.commit()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_runs_schema(conn)
    return conn


def list_runs(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> list[dict] | None:
    if not get_experiment(experiment_id, workspace_id, user_id, db_path=db_path):
        return None
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM experiment_runs WHERE experiment_id = ? AND workspace_id = ? "
            "AND owner_user_id = ? ORDER BY created_at, run_id",
            (experiment_id, workspace_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def create_run(
    experiment_id: str,
    workspace_id: str,
    user_id: str,
    title: str,
    *,
    status: str = "planned",
    planned: dict | None = None,
    actual: dict | None = None,
    observations: str = "",
    result: str = "",
    db_path: str | Path = DATABASE_PATH,
) -> dict:
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")
    if status not in RUN_STATUSES:
        raise ValueError("invalid status")
    experiment = get_experiment(experiment_id, workspace_id, user_id, db_path=db_path)
    if not experiment or experiment["owner_user_id"] != user_id:
        raise PermissionError("experiment access denied")
    conn = _connect(db_path)
    try:
        run_id = f"run_{uuid.uuid4().hex}"
        conn.execute(
            "INSERT INTO experiment_runs "
            "(run_id, experiment_id, workspace_id, owner_user_id, protocol_id, title, status, "
            "planned_json, actual_json, observations, result, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                run_id,
                experiment_id,
                workspace_id,
                user_id,
                experiment["protocol_id"],
                title,
                status,
                json.dumps(planned or {}, ensure_ascii=False),
                json.dumps(actual or {}, ensure_ascii=False),
                observations,
                result,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM experiment_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_run(
    run_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM experiment_runs WHERE run_id = ? AND workspace_id = ? "
            "AND owner_user_id = ?",
            (run_id, workspace_id, user_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_run(
    run_id: str,
    workspace_id: str,
    user_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    planned: dict | None = None,
    actual: dict | None = None,
    observations: str | None = None,
    result: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> dict | None:
    conn = _connect(db_path)
    try:
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
            assignments = ", ".join(f"{key} = ?" for key in fields)
            cursor = conn.execute(
                f"UPDATE experiment_runs SET {assignments}, updated_at = CURRENT_TIMESTAMP "
                "WHERE run_id = ? AND workspace_id = ? AND owner_user_id = ?",
                [*fields.values(), run_id, workspace_id, user_id],
            )
            conn.commit()
            if cursor.rowcount == 0:
                return None
        return get_run(run_id, workspace_id, user_id, db_path=db_path)
    finally:
        conn.close()
