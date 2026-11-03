"""Best-effort PostgreSQL sync for watch paper placeholder deletes.

Watch still writes through SQLite + outbox. This helper removes the placeholder
from PG immediately when present, then mirrors the SQLite delete; a missing PG
row is not an error.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class WatchWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_WATCH_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg_connection():
    from services.db.pg_pool import pg_connection

    return pg_connection(os.environ["SCIPAL_PG_DSN"])


def _pg():
    return _pg_connection()


def _ensure_id_sequence(pg, table: str) -> None:
    """Repair a serial sequence left behind by explicit-id outbox inserts."""
    if table not in {"watch_profiles", "watch_runs", "watch_items"}:
        raise ValueError("unsupported sequence table")
    seq_row = pg.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,)).fetchone()
    seq = seq_row["pg_get_serial_sequence"] if isinstance(seq_row, dict) else seq_row[0]
    pg.execute(
        f"SELECT setval(%s, COALESCE((SELECT max(id) FROM {table}), 0) + 1, false)",
        (seq,),
    )


def delete_paper_best_effort(paper_id: str, *, db_path: str | Path) -> bool:
    """Delete a watch placeholder in PG, then SQLite; return False if disabled.

    The SQLite delete still runs when PG is unavailable so the existing outbox
    can carry the delete later.
    """
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            row = pg.execute(
                "DELETE FROM papers WHERE paper_id = %s RETURNING paper_id", (paper_id,)
            ).fetchone()
            pg_deleted = bool(row)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch paper delete failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute("DELETE FROM papers WHERE paper_id = ?", (paper_id,))
        conn.commit()
    finally:
        conn.close()
    return pg_deleted


def create_profile(data: dict) -> int:
    try:
        with _pg() as pg:
            _ensure_id_sequence(pg, "watch_profiles")
            row = pg.execute(
                "INSERT INTO watch_profiles "
                "(owner,name,field_text,keywords,openalex_topic_ids,interval_days,window_days,"
                "top_journal_count,max_items,same_journal_limit,metric_type,metric_min,language,delivery,enabled,created_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (
                    data.get("owner") or "default", data.get("name"), data.get("field_text"),
                    data.get("keywords"), data.get("openalex_topic_ids"), data.get("interval_days"),
                    data.get("window_days"), data.get("top_journal_count"), data.get("max_items"),
                    data.get("same_journal_limit"), data.get("metric_type"), data.get("metric_min"),
                    data.get("language"), data.get("delivery"),
                    1 if data.get("enabled") is None else data.get("enabled"),
                    data.get("created_at"),
                ),
            ).fetchone()
            return int(row["id"])
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch profile create failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def update_profile(profile_id: int, updates: dict) -> None:
    assignments = ", ".join(f"{key} = %s" for key in updates)
    try:
        with _pg() as pg:
            row = pg.execute(
                f"UPDATE watch_profiles SET {assignments} WHERE id = %s RETURNING id",
                [*updates.values(), profile_id],
            ).fetchone()
        if not row:
            raise WatchWriteError("profile not found in PostgreSQL")
    except WatchWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch profile update failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def delete_profile(profile_id: int) -> None:
    try:
        with _pg() as pg:
            pg.execute("DELETE FROM watch_profile_journals WHERE profile_id=%s", (profile_id,))
            pg.execute("DELETE FROM watch_profiles WHERE id=%s", (profile_id,))
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch profile delete failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def create_run(row: dict) -> int:
    try:
        with _pg() as pg:
            _ensure_id_sequence(pg, "watch_runs")
            out = pg.execute(
                "INSERT INTO watch_runs (owner, profile_id, window_start, window_end, status, started_at) "
                "VALUES (%(owner)s, %(profile_id)s, %(window_start)s, %(window_end)s, 'running', %(started_at)s) "
                "RETURNING id",
                row,
            ).fetchone()
            return int(out["id"])
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch run create failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def update_run(run_id: int, updates: dict) -> None:
    assignments = ", ".join(f"{key} = %s" for key in updates)
    try:
        with _pg() as pg:
            row = pg.execute(
                f"UPDATE watch_runs SET {assignments} WHERE id = %s RETURNING id",
                [*updates.values(), run_id],
            ).fetchone()
        if not row:
            raise WatchWriteError("watch run not found in PostgreSQL")
    except WatchWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch run update failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def create_item(row: dict) -> int:
    try:
        with _pg() as pg:
            _ensure_id_sequence(pg, "watch_items")
            out = pg.execute(
                "INSERT INTO watch_items "
                "(owner, run_id, profile_id, paper_id, doi, title, journal, abstract, published, "
                "score, reason, acquisition, status) "
                "VALUES (%(owner)s, %(run_id)s, %(profile_id)s, %(paper_id)s, %(doi)s, %(title)s, "
                "%(journal)s, %(abstract)s, %(published)s, %(score)s, %(reason)s, %(acquisition)s, 'new') "
                "RETURNING id",
                row,
            ).fetchone()
            return int(out["id"])
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch item create failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def update_item(item_id: int, updates: dict) -> None:
    assignments = ", ".join(f"{key} = %s" for key in updates)
    try:
        with _pg() as pg:
            pg.execute(f"UPDATE watch_items SET {assignments} WHERE id = %s", [*updates.values(), item_id])
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch item update failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def mark_seen(row: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO watch_seen (profile_id, dedup_key, paper_id, first_seen_at, status) "
                "VALUES (%(profile_id)s, %(dedup_key)s, %(paper_id)s, %(first_seen_at)s, 'new') "
                "ON CONFLICT DO NOTHING",
                row,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch seen write failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def replace_journals(profile_id: int, entries: list[dict], added_at: str) -> None:
    try:
        with _pg() as pg:
            pg.execute("DELETE FROM watch_profile_journals WHERE profile_id=%s", (profile_id,))
            for entry in entries:
                pg.execute(
                    "INSERT INTO watch_profile_journals (profile_id, issn_l, name, source, added_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (profile_id, entry.get("issn_l"), entry.get("name"), entry.get("source", "auto"), added_at),
                )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch journals replace failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc


def delete_journal(profile_id: int, issn_l: str) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "DELETE FROM watch_profile_journals WHERE profile_id=%s AND issn_l=%s",
                (profile_id, issn_l),
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG watch journal delete failed; refusing SQLite fallback: %s", exc)
        raise WatchWriteError("watch write backend unavailable") from exc
