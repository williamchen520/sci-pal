"""PostgreSQL-primary review project writes (Phase 2, opt-in)."""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)


class ReviewWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_REVIEW_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["SCIPAL_PG_DSN"], row_factory=dict_row)


def create_project(row: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO review_projects (project_id, owner, name, field_text, pico_json, created_at) "
                "VALUES (%(project_id)s, %(owner)s, %(name)s, %(field_text)s, %(pico_json)s, %(created_at)s)",
                row,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG review project create failed; refusing SQLite fallback: %s", exc)
        raise ReviewWriteError("review write backend unavailable") from exc


def log_event(row: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO review_events (project_id, actor, action, target, detail, created_at) "
                "VALUES (%(project_id)s, %(actor)s, %(action)s, %(target)s, %(detail)s, %(created_at)s)",
                row,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG review event failed; refusing SQLite fallback: %s", exc)
        raise ReviewWriteError("review write backend unavailable") from exc
