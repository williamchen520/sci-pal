"""PostgreSQL read adapter for experiments (G3.6a)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.db.pg_pool import pg_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _workspace_role(pg, workspace_id: str, user_id: str) -> Optional[str]:
    row = pg.execute(
        "SELECT role FROM memberships WHERE workspace_id = %s AND user_id = %s AND status = 'active'",
        (workspace_id, user_id),
    ).fetchone()
    return row["role"] if row else None


def _project_access(pg, project_id: str, workspace_id: str, user_id: str) -> bool:
    project = pg.execute(
        "SELECT 1 FROM projects WHERE project_id = %s AND workspace_id = %s",
        (project_id, workspace_id),
    ).fetchone()
    if not project or not _workspace_role(pg, workspace_id, user_id):
        return False
    return bool(
        pg.execute(
            "SELECT 1 FROM project_members WHERE project_id = %s AND user_id = %s",
            (project_id, user_id),
        ).fetchone()
    )


def _active_approval(pg, experiment_id: str, workspace_id: str, user_id: str):
    return pg.execute(
        "SELECT * FROM experiment_access_requests "
        "WHERE experiment_id = %s AND workspace_id = %s AND requester_user_id = %s "
        "AND status = 'approved' AND expires_at IS NOT NULL AND expires_at > %s "
        "ORDER BY decided_at DESC LIMIT 1",
        (experiment_id, workspace_id, user_id, _now()),
    ).fetchone()


def list_experiments(project_id: str, workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    pg = pg_connection()
    try:
        if not _project_access(pg, project_id, workspace_id, user_id):
            return None
        rows = pg.execute(
            "SELECT * FROM experiments WHERE project_id = %s AND workspace_id = %s "
            "AND owner_user_id = %s ORDER BY updated_at DESC, experiment_id",
            (project_id, workspace_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def get_experiment(experiment_id: str, workspace_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    pg = pg_connection()
    try:
        row = pg.execute(
            "SELECT * FROM experiments WHERE experiment_id = %s AND workspace_id = %s",
            (experiment_id, workspace_id),
        ).fetchone()
        if not row:
            return None
        if row["owner_user_id"] == user_id or _active_approval(pg, experiment_id, workspace_id, user_id):
            return dict(row)
        return None
    finally:
        pg.close()


def list_revisions(experiment_id: str, workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    if not get_experiment(experiment_id, workspace_id, user_id):
        return None
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT revision_id, revision, hash, created_by, created_at, content "
            "FROM experiment_revisions WHERE experiment_id = %s AND workspace_id = %s "
            "ORDER BY revision DESC",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def get_audit(experiment_id: str, workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    if not get_experiment(experiment_id, workspace_id, user_id):
        return None
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT id, actor_user_id, action, revision, detail, created_at "
            "FROM experiment_audit WHERE experiment_id = %s AND workspace_id = %s ORDER BY id",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def list_signatures(experiment_id: str, workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    if not get_experiment(experiment_id, workspace_id, user_id):
        return None
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM experiment_signatures WHERE experiment_id = %s AND workspace_id = %s "
            "ORDER BY created_at DESC",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def list_access_requests(experiment_id: str, workspace_id: str, user_id: str) -> Optional[List[Dict[str, Any]]]:
    if not get_experiment(experiment_id, workspace_id, user_id):
        return None
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM experiment_access_requests WHERE experiment_id = %s AND workspace_id = %s "
            "ORDER BY created_at DESC",
            (experiment_id, workspace_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def list_workspace_requests(workspace_id: str, user_id: str) -> List[Dict[str, Any]]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM experiment_access_requests WHERE workspace_id = %s "
            "AND (owner_user_id = %s OR requester_user_id = %s) ORDER BY created_at DESC",
            (workspace_id, user_id, user_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
