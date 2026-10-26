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
    """
    CREATE TABLE IF NOT EXISTS experiment_runs (
        run_id       TEXT PRIMARY KEY,
        protocol_id  TEXT NOT NULL,
        title        TEXT,
        operator     TEXT,
        run_date     TEXT,
        status       TEXT NOT NULL DEFAULT 'planned',
        result       TEXT,
        notes        TEXT,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_experiment_runs_protocol "
    "ON experiment_runs (protocol_id, run_date DESC)",
    """
    CREATE TABLE IF NOT EXISTS experiment_run_files (
        file_id      TEXT PRIMARY KEY,
        run_id       TEXT NOT NULL,
        filename     TEXT,
        stored_name  TEXT NOT NULL,
        content_type TEXT,
        size         INTEGER,
        uploaded_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_experiment_run_files_run "
    "ON experiment_run_files (run_id, uploaded_at)",
)

RUN_STATUSES = ("planned", "running", "completed", "failed")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _run_status(value: Any) -> str:
    status = _text(value).lower() or "planned"
    return status if status in RUN_STATUSES else "planned"


def _done_steps(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def _run_row(row: Any) -> dict[str, Any]:
    record = dict(row)
    record["done_steps"] = _done_steps(record.get("done_steps"))
    return record


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _first(mapping: Mapping, *keys: str) -> str:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return _text(value)
    return ""


def _normalize_protocol_id(value: Any) -> str:
    """Accept ``325000``, ``protocols_io_325000`` or a /view/...-325000 URL.

    URL slugs may contain digits before the real id (``western-blot-2024-325000``),
    so trailing digits win over the first digit group.
    """
    import re as re_lib

    text = str(value or "").strip()
    for pattern in (r"(\d+)\s*$", r"protocols_io_(\d+)", r"(\d{2,})"):
        match = re_lib.search(pattern, text)
        if match:
            return match.group(1)
    return text


def _html_text(value: Any) -> str:
    """API returns step bodies as HTML (``<p>...</p>``); strip tags for storage."""
    import html as html_lib
    import re as re_lib

    text = html_lib.unescape(str(value or ""))
    text = re_lib.sub(r"<[^>]+>", " ", text)
    return re_lib.sub(r"\s+", " ", text).strip()


def _duration(value: Any) -> str:
    text = _text(value)
    return "" if text in {"0", "0:00", "0.0"} else text


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
    def __init__(
        self,
        db_path: str | Path,
        client: Any | None = None,
        storage_root: str | Path | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.client = client
        self.storage_root = (
            Path(storage_root) if storage_root else self.db_path.parent / "experiments"
        )

    def ensure_schema(self) -> None:
        with self._session() as conn:
            for statement in SCHEMA:
                conn.execute(statement)
            try:
                conn.execute("ALTER TABLE experiment_runs ADD COLUMN done_steps TEXT")
            except sqlite3.OperationalError:
                pass

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
            instructions = _html_text(
                _first(step, "step", "instructions", "description", "step_description", "text")
            )
            title_text = _first(step, "title", "name", "step_title", "section")
            if not title_text and instructions:
                title_text = instructions[:80]
            parsed_steps.append(
                {
                    "step_id": _first(step, "id", "step_id", "guid") or f"{protocol_id}_step_{ordinal}",
                    "ordinal": ordinal,
                    "title": title_text,
                    "instructions": instructions,
                    "duration": _duration(_first(step, "duration", "time", "duration_text")),
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
        normalized = _normalize_protocol_id(protocol_id)
        payload = fetch(normalized)
        return self.import_payload(
            payload,
            url=f"https://www.protocols.io/view/{normalized}",
        )

    def list(self, limit: int = 50, offset: int = 0, query: str = "") -> list[dict[str, Any]]:
        self.ensure_schema()
        where = ""
        params: list[Any] = []
        text = str(query or "").strip()
        if text:
            where = "WHERE p.title LIKE ? OR p.doi LIKE ?"
            params.extend([f"%{text}%", f"%{text}%"])
        params.extend([max(1, limit), max(0, offset)])
        with self._session() as conn:
            rows = conn.execute(
                f"""
                SELECT p.protocol_id, p.title, p.doi, p.version, p.url, p.fetched_at,
                       (SELECT COUNT(*) FROM protocol_steps s WHERE s.protocol_id = p.protocol_id) AS steps
                FROM protocol_imports p {where}
                ORDER BY p.fetched_at DESC LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def count(self, query: str = "") -> int:
        self.ensure_schema()
        text = str(query or "").strip()
        with self._session() as conn:
            if text:
                return int(
                    conn.execute(
                        "SELECT COUNT(*) FROM protocol_imports WHERE title LIKE ? OR doi LIKE ?",
                        (f"%{text}%", f"%{text}%"),
                    ).fetchone()[0]
                )
            return int(conn.execute("SELECT COUNT(*) FROM protocol_imports").fetchone()[0])

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

    # ------------------------------------------------------------------ runs
    def add_run(
        self,
        protocol_id: str,
        *,
        title: str = "",
        operator: str = "",
        run_date: str = "",
        status: str = "planned",
        result: str = "",
        notes: str = "",
        done_steps: Any = None,
    ) -> dict[str, Any]:
        import uuid

        self.ensure_schema()
        status = _run_status(status)
        run_id = "run_" + uuid.uuid4().hex[:12]
        now = _now()
        steps_done = _done_steps(done_steps)
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO experiment_runs
                (run_id, protocol_id, title, operator, run_date, status, result, notes, done_steps, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    protocol_id,
                    _text(title),
                    _text(operator),
                    _text(run_date) or now[:10],
                    status,
                    _text(result),
                    _text(notes),
                    json.dumps(steps_done, ensure_ascii=False),
                    now,
                    now,
                ),
            )
        return {
            "run_id": run_id,
            "protocol_id": protocol_id,
            "title": _text(title),
            "operator": _text(operator),
            "run_date": _text(run_date) or now[:10],
            "status": status,
            "result": _text(result),
            "notes": _text(notes),
            "done_steps": steps_done,
            "created_at": now,
            "updated_at": now,
        }

    def list_runs(self, protocol_id: str, limit: int = 50) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment_runs WHERE protocol_id = ? "
                "ORDER BY run_date DESC, created_at DESC LIMIT ?",
                (protocol_id, max(1, limit)),
            ).fetchall()
        return [_run_row(row) for row in rows]

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any] | None:
        allowed = {"title", "operator", "run_date", "status", "result", "notes", "done_steps"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if "status" in updates:
            updates["status"] = _run_status(updates["status"])
        if "done_steps" in updates:
            updates["done_steps"] = json.dumps(
                _done_steps(updates["done_steps"]), ensure_ascii=False
            )
        if not updates:
            return None
        self.ensure_schema()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = [str(value) for value in updates.values()]
        with self._session() as conn:
            cursor = conn.execute(
                f"UPDATE experiment_runs SET {assignments}, updated_at = ? WHERE run_id = ?",
                (*values, _now(), run_id),
            )
            if cursor.rowcount == 0:
                return None
            row = conn.execute(
                "SELECT * FROM experiment_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return _run_row(row) if row else None

    def delete_run(self, run_id: str) -> bool:
        self.ensure_schema()
        with self._session() as conn:
            cursor = conn.execute("DELETE FROM experiment_runs WHERE run_id = ?", (run_id,))
        return cursor.rowcount > 0

    def export_markdown(self, protocol_id: str) -> str | None:
        """Render one protocol (steps + runs) as a Markdown lab sheet."""
        record = self.get(protocol_id)
        if record is None:
            return None
        lines = [f"# {record.get('title') or protocol_id}", ""]
        meta = []
        if record.get("doi"):
            meta.append(f"DOI: {record['doi']}")
        if record.get("version"):
            meta.append(f"版本: {record['version']}")
        if record.get("license"):
            meta.append(f"许可: {record['license']}")
        if record.get("url"):
            meta.append(f"来源: {record['url']}")
        if meta:
            lines.extend([" · ".join(meta), ""])
        lines.extend(["## 步骤", ""])
        steps = record.get("steps") or []
        if not steps:
            lines.extend(["（该协议没有解析出步骤）", ""])
        for step in steps:
            lines.append(f"### {step['ordinal']}. {step.get('title') or '(未命名步骤)'}")
            if step.get("duration"):
                lines.append(f"- 时长：{step['duration']}")
            if step.get("reagents"):
                lines.append(f"- 试剂：{'、'.join(step['reagents'])}")
            if step.get("instructions"):
                lines.extend(["", step["instructions"]])
            lines.append("")
        runs = self.list_runs(protocol_id, limit=200)
        lines.extend(["## 实验记录", ""])
        if not runs:
            lines.append("（还没有实验记录）")
        else:
            lines.append("| 日期 | 标题 | 操作人 | 状态 | 步骤进度 | 结果 |")
            lines.append("|---|---|---|---|---|---|")
            for run in runs:
                done = len(run.get("done_steps") or [])
                lines.append(
                    f"| {run.get('run_date') or ''} | {run.get('title') or ''} | "
                    f"{run.get('operator') or ''} | {run.get('status') or ''} | "
                    f"{done}/{len(steps)} | {(run.get('result') or '').replace('|', '/')} |"
                )
        lines.append("")
        return "\n".join(lines)

    # ---------------------------------------------------------- attachments
    MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

    def add_attachment(
        self, run_id: str, filename: str, content_type: str, data: bytes
    ) -> dict[str, Any]:
        import re as re_lib
        import uuid

        self.ensure_schema()
        with self._session() as conn:
            exists = conn.execute(
                "SELECT 1 FROM experiment_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if not exists:
            raise ValueError("run not found")
        if len(data) > self.MAX_ATTACHMENT_BYTES:
            raise ValueError("file too large (max 20 MB)")
        safe = re_lib.sub(r"[^A-Za-z0-9._-]+", "_", Path(str(filename or "file")).name)[:120]
        safe = safe or "file"
        file_id = "file_" + uuid.uuid4().hex[:12]
        folder = self.storage_root / run_id
        folder.mkdir(parents=True, exist_ok=True)
        stored_name = f"{file_id}_{safe}"
        (folder / stored_name).write_bytes(data)
        now = _now()
        with self._session() as conn:
            conn.execute(
                """
                INSERT INTO experiment_run_files
                (file_id, run_id, filename, stored_name, content_type, size, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (file_id, run_id, safe, stored_name, _text(content_type), len(data), now),
            )
        return {
            "file_id": file_id,
            "run_id": run_id,
            "filename": safe,
            "content_type": _text(content_type),
            "size": len(data),
            "uploaded_at": now,
        }

    def list_attachments(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM experiment_run_files WHERE run_id = ? ORDER BY uploaded_at",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def attachment_path(self, run_id: str, file_id: str) -> Path | None:
        self.ensure_schema()
        with self._session() as conn:
            row = conn.execute(
                "SELECT stored_name FROM experiment_run_files WHERE run_id = ? AND file_id = ?",
                (run_id, file_id),
            ).fetchone()
        if row is None:
            return None
        path = self.storage_root / run_id / row["stored_name"]
        return path if path.exists() else None

    def delete_attachment(self, run_id: str, file_id: str) -> bool:
        path = self.attachment_path(run_id, file_id)
        self.ensure_schema()
        with self._session() as conn:
            cursor = conn.execute(
                "DELETE FROM experiment_run_files WHERE run_id = ? AND file_id = ?",
                (run_id, file_id),
            )
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                # Windows: file may still be held by a download response
                pass
        return cursor.rowcount > 0

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._session() as conn:
            rows = conn.execute(
                """
                SELECT r.*, p.title AS protocol_title
                FROM experiment_runs r
                LEFT JOIN protocol_imports p ON p.protocol_id = r.protocol_id
                ORDER BY r.run_date DESC, r.created_at DESC LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        return [_run_row(row) for row in rows]

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
