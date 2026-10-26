"""Persistent storage for generated reviews.

``ReviewStore`` is an in-process, TTL-limited cache used by the web API for
citation tracing. This repository is the durable half: a ``reviews`` table in
``research.db`` that survives process exit, so reviews produced by the CLI (or
by an external client) remain readable.

Schema is created lazily (``CREATE TABLE IF NOT EXISTS``) so existing databases
gain the table on first use without a migration step.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS reviews (
        review_id       TEXT PRIMARY KEY,
        run_id          TEXT,
        topic           TEXT NOT NULL,
        markdown        TEXT NOT NULL,
        stats_json      TEXT,
        references_json TEXT,
        warnings_json   TEXT,
        guard_json      TEXT,
        created_at      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews (created_at DESC)",
)


class ReviewRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def ensure_schema(self) -> None:
        with self._session() as conn:
            for statement in SCHEMA:
                conn.execute(statement)
            try:
                conn.execute("ALTER TABLE reviews ADD COLUMN guard_json TEXT")
            except sqlite3.OperationalError:
                pass

    def save(
        self,
        *,
        review_id: str,
        topic: str,
        markdown: str,
        run_id: str | None = None,
        stats: Mapping[str, Any] | None = None,
        references: list[dict[str, Any]] | None = None,
        warnings: list[str] | None = None,
        guard: Mapping[str, Any] | None = None,
        created_at: str | None = None,
    ) -> str:
        self.ensure_schema()
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reviews
                    (review_id, run_id, topic, markdown, stats_json,
                     references_json, warnings_json, guard_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    run_id,
                    topic,
                    markdown,
                    _dump(stats or {}),
                    _dump(references or []),
                    _dump(warnings or []),
                    _dump(guard) if guard is not None else None,
                    created_at or _now(),
                ),
            )
        return review_id

    def get(self, review_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM reviews WHERE review_id = ?", (review_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "review_id": row["review_id"],
        "run_id": row["run_id"],
        "topic": row["topic"],
        "markdown": row["markdown"],
        "stats": _load(row["stats_json"], {}),
        "references": _load(row["references_json"], []),
        "warnings": _load(row["warnings_json"], []),
        "guard": _load(row["guard_json"], None),
        "created_at": row["created_at"],
    }


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

