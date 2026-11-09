"""Durable reference library (PostgreSQL only)."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from services.db.pg_pool import pg_connection
from services.db.tenant_pilot import set_search_path


def _pg():
    pg = pg_connection()
    set_search_path(pg, "references")
    return pg


class ReferenceLibrary:
    def __init__(self, db_path=None) -> None:
        # db_path is kept for call-site compatibility; storage is PostgreSQL.
        self.db_path = db_path

    def ensure_schema(self) -> None:
        return None

    def import_references(
        self,
        references: Iterable[Any],
        *,
        source: str = "ris",
    ) -> dict[str, int]:
        added = skipped = 0
        pg = _pg()
        try:
            for reference in references:
                doi = _clean(getattr(reference, "doi", "") or _dict(reference).get("doi"))
                title = _clean(getattr(reference, "title", "") or _dict(reference).get("title"))
                if not doi and not title:
                    skipped += 1
                    continue
                key = doi.lower() if doi else f"title:{title.lower()}|{_year(reference)}"
                reference_id = "ref_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
                row = pg.execute(
                    "INSERT INTO reference_library "
                    "(reference_id, doi, title, authors, journal, year, abstract, source, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING "
                    "RETURNING reference_id",
                    (
                        reference_id, doi, title, _authors(reference),
                        _clean(getattr(reference, "journal", "") or _dict(reference).get("journal")),
                        _year(reference),
                        _clean(getattr(reference, "abstract", "") or _dict(reference).get("abstract")),
                        source, _now(),
                    ),
                ).fetchone()
                if row:
                    added += 1
                else:
                    skipped += 1
            pg.commit()
        finally:
            pg.close()
        return {"added": added, "skipped": skipped}

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        pg = _pg()
        try:
            rows = pg.execute(
                "SELECT * FROM reference_library ORDER BY created_at DESC LIMIT %s",
                (max(1, limit),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            pg.close()

    def count(self) -> int:
        pg = _pg()
        try:
            return int(pg.execute("SELECT COUNT(*) AS n FROM reference_library").fetchone()["n"])
        finally:
            pg.close()


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
