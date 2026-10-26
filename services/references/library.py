"""Durable reference library (imported from RIS / EndNote XML)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS reference_library (
        reference_id TEXT PRIMARY KEY,
        doi          TEXT,
        title        TEXT,
        authors      TEXT,
        journal      TEXT,
        year         TEXT,
        abstract     TEXT,
        source       TEXT,
        created_at   TEXT NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_reference_library_doi "
    "ON reference_library (doi) WHERE doi IS NOT NULL AND doi != ''",
)


class ReferenceLibrary:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def ensure_schema(self) -> None:
        with self._session() as conn:
            for statement in SCHEMA:
                conn.execute(statement)

    def import_references(
        self,
        references: Iterable[Any],
        *,
        source: str = "ris",
    ) -> dict[str, int]:
        self.ensure_schema()
        added = skipped = 0
        with self._session() as conn:
            for reference in references:
                doi = _clean(getattr(reference, "doi", "") or _dict(reference).get("doi"))
                title = _clean(getattr(reference, "title", "") or _dict(reference).get("title"))
                if not doi and not title:
                    skipped += 1
                    continue
                key = doi.lower() if doi else f"title:{title.lower()}|{_year(reference)}"
                reference_id = "ref_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
                try:
                    conn.execute(
                        """
                        INSERT INTO reference_library
                        (reference_id, doi, title, authors, journal, year, abstract, source, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            reference_id,
                            doi,
                            title,
                            _authors(reference),
                            _clean(getattr(reference, "journal", "") or _dict(reference).get("journal")),
                            _year(reference),
                            _clean(getattr(reference, "abstract", "") or _dict(reference).get("abstract")),
                            source,
                            _now(),
                        ),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    skipped += 1
        return {"added": added, "skipped": skipped}

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM reference_library ORDER BY created_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        self.ensure_schema()
        with self._session() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM reference_library").fetchone()[0])

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
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


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _authors(reference: Any) -> str:
    value = getattr(reference, "authors", None) or _dict(reference).get("authors") or ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item) for item in value)
    return str(value)


def _year(reference: Any) -> str:
    return _clean(getattr(reference, "year", "") or _dict(reference).get("year"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
