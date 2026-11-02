"""PostgreSQL-primary experiment writes (Phase 1, opt-in).

PG is written first for create/update; SQLite remains the read/mirror store.
"""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)


class ExperimentWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_EXPERIMENT_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["SCIPAL_PG_DSN"], row_factory=dict_row)


def create_experiment(experiment: dict, revision: dict, audit: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO experiments "
                "(experiment_id, project_id, workspace_id, owner_user_id, title, status, "
                "protocol_id, protocol_version, content, data_class, current_revision, "
                "created_at, updated_at) "
                "VALUES (%(experiment_id)s, %(project_id)s, %(workspace_id)s, %(owner_user_id)s, "
                "%(title)s, %(status)s, %(protocol_id)s, %(protocol_version)s, %(content)s, "
                "'private', 1, %(created_at)s, %(updated_at)s)",
                experiment,
            )
            pg.execute(
                "INSERT INTO experiment_revisions "
                "(revision_id, experiment_id, workspace_id, revision, content, hash, created_by, created_at) "
                "VALUES (%(revision_id)s, %(experiment_id)s, %(workspace_id)s, %(revision)s, "
                "%(content)s, %(hash)s, %(created_by)s, %(created_at)s)",
                revision,
            )
            pg.execute(
                "INSERT INTO experiment_audit "
                "(experiment_id, workspace_id, actor_user_id, action, revision, detail, created_at) "
                "VALUES (%(experiment_id)s, %(workspace_id)s, %(actor_user_id)s, %(action)s, "
                "%(revision)s, %(detail)s, %(created_at)s)",
                audit,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG experiment create failed; refusing SQLite fallback: %s", exc)
        raise ExperimentWriteError("experiment write backend unavailable") from exc


def update_experiment(
    experiment_id: str, workspace_id: str, fields: dict, revision: dict, audit: dict
) -> None:
    assignments = ", ".join(f"{key} = %s" for key in fields)
    try:
        with _pg() as pg:
            row = pg.execute(
                f"UPDATE experiments SET {assignments}, current_revision = %s, updated_at = %s "
                "WHERE experiment_id = %s AND workspace_id = %s RETURNING experiment_id",
                [*fields.values(), revision["revision"], revision["created_at"], experiment_id, workspace_id],
            ).fetchone()
            if not row:
                raise ExperimentWriteError("experiment not found in PostgreSQL")
            pg.execute(
                "INSERT INTO experiment_revisions "
                "(revision_id, experiment_id, workspace_id, revision, content, hash, created_by, created_at) "
                "VALUES (%(revision_id)s, %(experiment_id)s, %(workspace_id)s, %(revision)s, "
                "%(content)s, %(hash)s, %(created_by)s, %(created_at)s)",
                revision,
            )
            pg.execute(
                "INSERT INTO experiment_audit "
                "(experiment_id, workspace_id, actor_user_id, action, revision, detail, created_at) "
                "VALUES (%(experiment_id)s, %(workspace_id)s, %(actor_user_id)s, %(action)s, "
                "%(revision)s, %(detail)s, %(created_at)s)",
                audit,
            )
    except ExperimentWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG experiment update failed; refusing SQLite fallback: %s", exc)
        raise ExperimentWriteError("experiment write backend unavailable") from exc


def create_access_request(request: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO experiment_access_requests "
                "(request_id, experiment_id, workspace_id, requester_user_id, owner_user_id, status, scope, created_at) "
                "VALUES (%(request_id)s, %(experiment_id)s, %(workspace_id)s, %(requester_user_id)s, "
                "%(owner_user_id)s, 'pending', 'read', %(created_at)s)",
                request,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG access request create failed; refusing SQLite fallback: %s", exc)
        raise ExperimentWriteError("experiment write backend unavailable") from exc


def decide_access_request(request_id: str, status: str, decided_at: str, expires_at: str | None) -> None:
    try:
        with _pg() as pg:
            row = pg.execute(
                "UPDATE experiment_access_requests SET status=%s, decided_at=%s, expires_at=%s "
                "WHERE request_id=%s RETURNING request_id",
                (status, decided_at, expires_at, request_id),
            ).fetchone()
        if not row:
            raise ExperimentWriteError("access request not found in PostgreSQL")
    except ExperimentWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG access request decision failed; refusing SQLite fallback: %s", exc)
        raise ExperimentWriteError("experiment write backend unavailable") from exc


def create_signature(signature: dict, audit: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO experiment_signatures "
                "(signature_id, experiment_id, workspace_id, revision, signer_user_id, meaning, "
                "record_hash, signature_hash, created_at) "
                "VALUES (%(signature_id)s, %(experiment_id)s, %(workspace_id)s, %(revision)s, "
                "%(signer_user_id)s, %(meaning)s, %(record_hash)s, %(signature_hash)s, %(created_at)s)",
                signature,
            )
            pg.execute(
                "INSERT INTO experiment_audit "
                "(experiment_id, workspace_id, actor_user_id, action, revision, detail, created_at) "
                "VALUES (%(experiment_id)s, %(workspace_id)s, %(actor_user_id)s, %(action)s, "
                "%(revision)s, %(detail)s, %(created_at)s)",
                audit,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG signature create failed; refusing SQLite fallback: %s", exc)
        raise ExperimentWriteError("experiment write backend unavailable") from exc
