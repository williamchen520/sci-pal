"""PostgreSQL-primary project writes (Phase 1, opt-in).

SQLite stays a read/mirror store. When enabled, PG is written first and a PG
failure aborts before SQLite is touched.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

LOGGER = logging.getLogger(__name__)


class ProjectWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_PROJECT_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg():
    from services.db.pg_pool import pg_connection

    return pg_connection(os.environ["SCIPAL_PG_DSN"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(project_id: str, workspace_id: str, owner_user_id: str, name: str, description: str, status: str) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO projects (project_id, workspace_id, owner_user_id, name, description, status) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (project_id, workspace_id, owner_user_id, name, description, status),
            )
            pg.execute(
                "INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, 'owner')",
                (project_id, owner_user_id),
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG project create failed; refusing SQLite fallback: %s", exc)
        raise ProjectWriteError("project write backend unavailable") from exc


def update_project(project_id: str, workspace_id: str, fields: dict) -> bool:
    if not fields:
        return False
    assignments = ", ".join(f"{key} = %s" for key in fields)
    try:
        with _pg() as pg:
            row = pg.execute(
                f"UPDATE projects SET {assignments}, updated_at = %s "
                "WHERE project_id = %s AND workspace_id = %s RETURNING project_id",
                [*fields.values(), _now(), project_id, workspace_id],
            ).fetchone()
        if not row:
            raise ProjectWriteError("project not found in PostgreSQL")
        return True
    except ProjectWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG project update failed; refusing SQLite fallback: %s", exc)
        raise ProjectWriteError("project write backend unavailable") from exc


def add_member(project_id: str, user_id: str, role: str) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, %s) "
                "ON CONFLICT (project_id, user_id) DO UPDATE SET role = EXCLUDED.role",
                (project_id, user_id, role),
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG project member write failed; refusing SQLite fallback: %s", exc)
        raise ProjectWriteError("project write backend unavailable") from exc


def copy_project(
    new_id: str,
    workspace_id: str,
    actor_user_id: str,
    name: str,
    description: str,
    data_class: str,
    source_id: str,
) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO projects "
                "(project_id, workspace_id, owner_user_id, name, description, status, data_class, copied_from) "
                "VALUES (%s, %s, %s, %s, %s, 'planning', %s, %s)",
                (new_id, workspace_id, actor_user_id, name, description, data_class, source_id),
            )
            pg.execute(
                "INSERT INTO project_members (project_id, user_id, role) VALUES (%s, %s, 'owner')",
                (new_id, actor_user_id),
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG project copy failed; refusing SQLite fallback: %s", exc)
        raise ProjectWriteError("project write backend unavailable") from exc
