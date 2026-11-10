"""Ingest task store: PostgreSQL by default, SQLite factory for tests."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

_FACTORY = None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class PGTaskStore:
    def __init__(self, db_path=None) -> None:
        pass

    def _pg(self):
        from services.db.pg_pool import pg_connection

        return pg_connection()

    def create(self, task_id: str, *, total: int, batch_size: int, pmc_ids: str) -> None:
        pg = self._pg()
        try:
            pg.execute(
                "INSERT INTO ingest_tasks "
                "(task_id,status,total,batch_size,pmc_ids,created_at,updated_at) "
                "VALUES (%s,'queued',%s,%s,%s,%s,%s)",
                (task_id, total, batch_size, pmc_ids, _now(), _now()),
            )
            pg.commit()
        finally:
            pg.close()

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        pg = self._pg()
        try:
            row = pg.execute("SELECT * FROM ingest_tasks WHERE task_id=%s", (task_id,)).fetchone()
            return dict(row) if row else None
        finally:
            pg.close()

    def set(self, task_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = %s" for key in fields)
        pg = self._pg()
        try:
            pg.execute(
                f"UPDATE ingest_tasks SET {assignments} WHERE task_id = %s",
                (*fields.values(), task_id),
            )
            pg.commit()
        finally:
            pg.close()

    def cancel(self, task_id: str) -> bool:
        pg = self._pg()
        try:
            cur = pg.execute(
                "UPDATE ingest_tasks SET cancel_requested=1, updated_at=%s WHERE task_id=%s",
                (_now(), task_id),
            )
            pg.commit()
            return cur.rowcount > 0
        finally:
            pg.close()

    def cancelled(self, task_id: str) -> bool:
        pg = self._pg()
        try:
            row = pg.execute(
                "SELECT cancel_requested FROM ingest_tasks WHERE task_id=%s", (task_id,)
            ).fetchone()
            return bool(row and row["cancel_requested"])
        finally:
            pg.close()


def configure(factory) -> None:
    global _FACTORY
    _FACTORY = factory


def task_store_for(db_path) -> Any:
    return _FACTORY(db_path) if _FACTORY else PGTaskStore(db_path)
