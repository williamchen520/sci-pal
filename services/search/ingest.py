"""Batch download + vectorise pipeline with explicit, resumable commits.

Design constraints (from the 2026-10-25 incident):

* submit-only: :meth:`IngestService.start` returns a ``task_id`` immediately and
  the work happens on a background thread;
* batch commits: every ``batch_size`` papers are downloaded, parsed, written in
  one SQLite transaction, then embedded — never one giant transaction at the end;
* failure isolation: a broken batch rolls back only itself, earlier batches stay;
* SQLite WAL + ``synchronous=NORMAL`` so a killed process cannot leave a
  half-written journal behind.

The service is dependency-injectable (``download`` / ``parse`` / ``embed``) so
the batch and rollback behaviour can be tested without network or models.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

DEFAULT_BATCH_SIZE = 5
MAX_BATCH_SIZE = 25
RUN_LOCK = threading.Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class IngestService:
    def __init__(
        self,
        *,
        db_path: str | Path,
        xml_dir: str | Path,
        chroma_path: str | Path | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        download: Callable[[str], Path | None] | None = None,
        parse: Callable[[Path], Mapping[str, Any] | None] | None = None,
        embed: Callable[[Sequence[Mapping[str, Any]]], int] | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.db_path = Path(db_path)
        self.xml_dir = Path(xml_dir)
        self.chroma_path = Path(chroma_path) if chroma_path else None
        self.default_batch_size = _clamp_batch(batch_size)
        self._download = download
        self._parse = parse
        self._embed = embed
        self.log = log

    # ---------------------------------------------------------------- submit
    def start(
        self,
        pmc_ids: Iterable[str],
        *,
        batch_size: int | None = None,
    ) -> str:
        ids = [str(value).strip() for value in pmc_ids if str(value).strip()]
        if not ids:
            raise ValueError("pmc_ids must not be empty")

        task_id = f"ing_{uuid.uuid4().hex[:12]}"
        size = _clamp_batch(batch_size or self.default_batch_size)
        conn = self._connect()
        try:
            _ensure_schema(conn)
            conn.execute(
                """
                INSERT INTO ingest_tasks
                (task_id, status, total, batch_size, pmc_ids, created_at, updated_at)
                VALUES (?, 'queued', ?, ?, ?, ?, ?)
                """,
                (task_id, len(ids), size, json.dumps(ids), _now(), _now()),
            )
            conn.commit()
        finally:
            conn.close()

        thread = threading.Thread(
            target=self._run, args=(task_id, ids, size), name=f"ingest-{task_id}", daemon=True
        )
        thread.start()
        self.log(f"ingest queued: {task_id} ({len(ids)} papers, batch={size})")
        return task_id

    # ------------------------------------------------------------------ work
    def _run(self, task_id: str, pmc_ids: list[str], batch_size: int) -> None:
        conn = self._connect()
        try:
            _ensure_schema(conn)
            with RUN_LOCK:
                self._set(conn, task_id, status="running")
                failures: list[dict[str, str]] = []
                processed = imported = 0
                for start in range(0, len(pmc_ids), batch_size):
                    if self._cancelled(conn, task_id):
                        self._set(conn, task_id, status="cancelled")
                        return
                    batch = pmc_ids[start:start + batch_size]
                    parsed = self._download_batch(batch, failures)
                    try:
                        written = self._write_batch(conn, parsed)
                    except Exception as exc:  # noqa: BLE001 - roll back this batch only
                        conn.rollback()
                        for item in parsed:
                            failures.append({"pmc_id": item["pmc_id"], "error": f"db: {exc}"})
                        written = 0
                    embedded = 0
                    try:
                        embedded = self._embed_batch(parsed)
                    except Exception as exc:  # noqa: BLE001 - index can be rebuilt later
                        for item in parsed:
                            failures.append({"pmc_id": item["pmc_id"], "error": f"embed: {exc}"})

                    processed += len(batch)
                    imported += written
                    self.log(
                        f"{task_id}: batch {start // batch_size + 1} "
                        f"written={written} embedded={embedded}"
                    )
                    self._set(
                        conn,
                        task_id,
                        processed=processed,
                        imported=imported,
                        failed=len(failures),
                        current=f"batch {start // batch_size + 1}",
                    )

                if imported and failures:
                    status = "partial"
                elif imported:
                    status = "completed"
                else:
                    status = "failed"
                self._set(
                    conn,
                    task_id,
                    status=status,
                    processed=processed,
                    imported=imported,
                    failed=len(failures),
                    current=None,
                    error=json.dumps(failures[:20], ensure_ascii=False) if failures else None,
                )
        except Exception as exc:  # noqa: BLE001 - worker thread must always end in a known state
            try:
                self._set(conn, task_id, status="failed", error=str(exc))
            except Exception:
                pass
            self.log(f"{task_id} failed: {exc}")
        finally:
            conn.close()

    def _download_batch(
        self, batch: Sequence[str], failures: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for pmc_id in batch:
            try:
                path = (self._download or self._default_download)(pmc_id)
                if not path:
                    failures.append({"pmc_id": pmc_id, "error": "download failed"})
                    continue
                data = (self._parse or self._default_parse)(path)
                if not data or not data.get("title"):
                    failures.append({"pmc_id": pmc_id, "error": "no title"})
                    continue
                parsed.append({"pmc_id": pmc_id, "data": data})
            except Exception as exc:  # noqa: BLE001 - one bad paper must not kill the batch
                failures.append({"pmc_id": pmc_id, "error": str(exc)[:200]})
        return parsed

    def _write_batch(self, conn: sqlite3.Connection, parsed: Sequence[Mapping[str, Any]]) -> int:
        written = 0
        with conn:  # BEGIN ... COMMIT; any exception rolls the whole batch back
            for item in parsed:
                data = item["data"]
                paper_id = _paper_id(item["pmc_id"])
                conn.execute(
                    """
                    INSERT OR REPLACE INTO papers
                    (paper_id, filename, title, abstract, authors, parse_engine)
                    VALUES (?, ?, ?, ?, ?, 'xml')
                    """,
                    (
                        paper_id,
                        f"{item['pmc_id']}.xml",
                        data.get("title"),
                        data.get("abstract") or "",
                        data.get("authors") or "",
                    ),
                )
                conn.execute("DELETE FROM paragraphs WHERE paper_id = ?", (paper_id,))
                for index, para in enumerate(data.get("paragraphs") or []):
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO paragraphs
                        (para_id, paper_id, section_level1, text, sequence, parse_engine)
                        VALUES (?, ?, ?, ?, ?, 'xml')
                        """,
                        (
                            f"{paper_id}_para_{index:05d}",
                            paper_id,
                            para.get("section") or "",
                            para.get("text") or "",
                            para.get("sequence") or index,
                        ),
                    )
                written += 1
        return written

    def _embed_batch(self, parsed: Sequence[Mapping[str, Any]]) -> int:
        if not parsed:
            return 0
        rows: list[dict[str, Any]] = []
        for item in parsed:
            paper_id = _paper_id(item["pmc_id"])
            for index, para in enumerate(item["data"].get("paragraphs") or []):
                rows.append(
                    {
                        "para_id": f"{paper_id}_para_{index:05d}",
                        "paper_id": paper_id,
                        "text": para.get("text") or "",
                        "section": para.get("section") or "",
                    }
                )
        rows = [row for row in rows if row["text"].strip()]
        if not rows:
            return 0
        embedder = self._embed or self._default_embed
        return int(embedder(rows))

    # ----------------------------------------------------------------- real IO
    def _default_download(self, pmc_id: str) -> Path | None:
        from download_pmc_xml import PMCXMLDownloader

        target = self.xml_dir / f"{pmc_id}.xml"
        if target.exists() and target.stat().st_size > 1024:
            return target
        downloader = PMCXMLDownloader(output_dir=str(self.xml_dir), verbose=False)
        return target if downloader.download_xml(pmc_id) else None

    def _default_parse(self, path: Path) -> Mapping[str, Any] | None:
        from import_xml_v2 import parse_jats_xml

        return parse_jats_xml(path)

    def _default_embed(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not self.chroma_path:
            return 0
        import chromadb
        from sentence_transformers import SentenceTransformer

        model_path = Path(r"D:\models\models\BAAI--bge-base-en-v1.5")
        model = getattr(self, "_model", None)
        if model is None:
            model = SentenceTransformer(str(model_path))
            self._model = model
        client = chromadb.PersistentClient(path=str(self.chroma_path))
        collection = client.get_collection("paragraphs")
        documents = [row["text"] for row in rows]
        embeddings = model.encode(documents, show_progress_bar=False).tolist()
        collection.add(
            ids=[row["para_id"] for row in rows],
            documents=documents,
            metadatas=[
                {
                    "paper_id": row["paper_id"],
                    "section_l1": row["section"],
                    "section_l2": "",
                }
                for row in rows
            ],
            embeddings=embeddings,
        )
        return len(rows)

    # ---------------------------------------------------------------- status
    def status(self, task_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            _ensure_schema(conn)
            row = conn.execute("SELECT * FROM ingest_tasks WHERE task_id = ?", (task_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def cancel(self, task_id: str) -> bool:
        conn = self._connect()
        try:
            _ensure_schema(conn)
            cur = conn.execute(
                "UPDATE ingest_tasks SET cancel_requested = 1, updated_at = ? WHERE task_id = ?",
                (_now(), task_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # --------------------------------------------------------------- helpers
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _cancelled(self, conn: sqlite3.Connection, task_id: str) -> bool:
        row = conn.execute(
            "SELECT cancel_requested FROM ingest_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return bool(row and row["cancel_requested"])

    def _set(self, conn: sqlite3.Connection, task_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        conn.execute(
            f"UPDATE ingest_tasks SET {assignments} WHERE task_id = ?",
            (*fields.values(), task_id),
        )
        conn.commit()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ingest_tasks (
            task_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            processed INTEGER NOT NULL DEFAULT 0,
            imported INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            batch_size INTEGER NOT NULL DEFAULT 5,
            current TEXT,
            error TEXT,
            pmc_ids TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _paper_id(pmc_id: str) -> str:
    import hashlib

    digest = hashlib.md5(pmc_id.encode()).hexdigest()[:8]
    return f"paper_{pmc_id}_{digest}_xml"


def _clamp_batch(value: int) -> int:
    return max(1, min(int(value), MAX_BATCH_SIZE))
