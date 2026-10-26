"""protocols.io import storage (P1).

Only imported protocols are cached locally; we do not mirror the remote library.
The parser is tolerant: API v3 wraps the object in ``{"protocol": ...}`` and
field names have drifted across versions, so each field has fallbacks.
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
    CREATE TABLE IF NOT EXISTS protocol_imports (
        protocol_id TEXT PRIMARY KEY,
        title       TEXT,
        doi         TEXT,
        version     TEXT,
        url         TEXT,
        license     TEXT,
        fetched_at  TEXT NOT NULL,
        raw_json    TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS protocol_steps (
        step_id      TEXT PRIMARY KEY,
        protocol_id  TEXT NOT NULL,
        ordinal      INTEGER NOT NULL,
        title        TEXT,
        instructions TEXT,
        duration     TEXT,
        reagents_json TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_protocol_steps_protocol ON protocol_steps (protocol_id, ordinal)",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(mapping: Mapping, *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return _text(value)
    return ""


def _reagents(step: Mapping) -> list[str]:
    for key in ("reagents", "components", "materials", "reagents_list"):
        value = step.get(key)
        if isinstance(value, list):
            result = []
            for item in value:
                if isinstance(item, Mapping):
                    result.append(_first(item, "name", "title", "reagent"))
                else:
                    result.append(_text(item))
            return [item for item in result if item]
    return []


class ProtocolService:
    def __init__(self, db_path: str | Path, client: Any | None = None) -> None:
        self.db_path = Path(db_path)
        self.client = client

    def ensure_schema(self) -> None:
        with self._session() as conn:
            for statement in SCHEMA:
                conn.execute(statement)

    def import_payload(self, payload: Mapping[str, Any], *, url: str = "") -> dict[str, Any]:
        """Parse and store one protocol payload (already fetched or a fixture)."""
        protocol = payload.get("protocol") if isinstance(payload.get("protocol"), Mapping) else payload
        protocol_id = _first(protocol, "id", "protocol_id", "guid") or _first(
            payload, "protocol_id"
        )
        if not protocol_id:
            raise ValueError("payload has no protocol id")
        title = _first(protocol, "title", "name")
        try:
            doi = _first(protocol.get("doi") or {}, "doi") if isinstance(protocol.get("doi"), Mapping) else _text(protocol.get("doi"))
        except Exception:  # noqa: BLE001
            doi = ""
        steps = protocol.get("steps") or payload.get("steps") or []
        if isinstance(steps, Mapping):
            steps = steps.get("steps") or []
        parsed_steps = []
        for ordinal, step in enumerate(steps, 1):
            if not isinstance(step, Mapping):
                continue
            parsed_steps.append(
                {
                    "step_id": _first(step, "id", "step_id", "guid") or f"{protocol_id}_step_{ordinal}",
                    "ordinal": ordinal,
                    "title": _first(step, "title", "name", "step_title"),
                    "instructions": _first(
                        step, "instructions", "description", "step_description", "text"
                    ),
                    "duration": _first(step, "duration", "time", "duration_text"),
                    "reagents": _reagents(step),
                }
            )
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.ensure_schema()
        with self._session() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO protocol_imports
                (protocol_id, title, doi, version, url, license, fetched_at, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    protocol_id,
                    title,
                    doi,
                    _first(protocol, "version", "version_id", "v"),
                    url or _first(protocol, "url", "link"),
                    _first(protocol, "license", "license_name"),
                    now,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.execute("DELETE FROM protocol_steps WHERE protocol_id = ?", (protocol_id,))
            for step in parsed_steps:
                conn.execute(
                    """
                    INSERT INTO protocol_steps
                    (step_id, protocol_id, ordinal, title, instructions, duration, reagents_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step["step_id"],
                        protocol_id,
                        step["ordinal"],
                        step["title"],
                        step["instructions"],
                        step["duration"],
                        json.dumps(step["reagents"], ensure_ascii=False),
                    ),
                )
        return {"protocol_id": protocol_id, "title": title, "steps": len(parsed_steps)}

    def import_protocol(self, protocol_id: str) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError(
                "protocols.io client 未配置：设置 SCIPAL_PROTOCOLS_IO_TOKEN 后重试"
            )
        fetch = getattr(self.client, "fetch_protocol", None)
        if fetch is None:
            raise RuntimeError("client does not support fetch_protocol")
        payload = fetch(protocol_id)
        return self.import_payload(payload, url=f"https://www.protocols.io/view/{protocol_id}")

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT p.protocol_id, p.title, p.doi, p.version, p.url, p.fetched_at,
                       (SELECT COUNT(*) FROM protocol_steps s WHERE s.protocol_id = p.protocol_id) AS steps
                FROM protocol_imports p ORDER BY p.fetched_at DESC LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, protocol_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._session() as conn:
            row = conn.execute(
                "SELECT * FROM protocol_imports WHERE protocol_id = ?", (protocol_id,)
            ).fetchone()
            if row is None:
                return None
            record = dict(row)
            record["steps"] = [
                {
                    **dict(step),
                    "reagents": json.loads(step["reagents_json"] or "[]"),
                }
                for step in conn.execute(
                    "SELECT * FROM protocol_steps WHERE protocol_id = ? ORDER BY ordinal",
                    (protocol_id,),
                )
            ]
            record.pop("raw_json", None)
        return record

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
