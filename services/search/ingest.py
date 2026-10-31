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
import os
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
        embed_client: Callable[[Sequence[Mapping[str, Any]]], int] | None = None,
        batch_timeout: float = 300.0,
        download_retries: int | None = None,
        download_retry_delay: float = 2.0,
        queue_dir: str | Path | None = None,
        log: Callable[[str], None] = print,
    ) -> None:
        self.db_path = Path(db_path)
        self.xml_dir = Path(xml_dir)
        self.chroma_path = Path(chroma_path) if chroma_path else None
        self.queue_dir = Path(queue_dir) if queue_dir else None
        self.default_batch_size = _clamp_batch(batch_size)
        self._download = download
        self._parse = parse
        self._embed = embed
        self._embed_client = embed_client
        self.batch_timeout = float(batch_timeout)
        self.download_retries = int(
            download_retries
            if download_retries is not None
            else os.environ.get("SCIPAL_DOWNLOAD_RETRIES", "3")
        )
        self.download_retry_delay = float(download_retry_delay)
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

        self.log(f"ingest queued: {task_id} ({len(ids)} papers, batch={size})")
        if self.queue_dir is not None:
            self._enqueue_job(task_id, ids, size)
            return task_id

        thread = threading.Thread(
            target=self._run, args=(task_id, ids, size), name=f"ingest-{task_id}", daemon=True
        )
        thread.start()
        return task_id

    def _enqueue_job(self, task_id: str, ids: list[str], size: int) -> None:
        """Hand the job to the resident worker (Flask stays out of the CPU path)."""
        queue = Path(self.queue_dir)
        queue.mkdir(parents=True, exist_ok=True)
        payload = {
            "type": "ingest",
            "task_id": task_id,
            "pmc_ids": ids,
            "batch_size": size,
        }
        path = queue / f"ingest-{task_id}.job.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        self.log(f"ingest job queued for worker: {path.name}")

    def execute(self, task_id: str) -> dict[str, Any] | None:
        """Run an already-created task (called by the worker)."""
        conn = self._connect()
        try:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT status, pmc_ids, batch_size FROM ingest_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown ingest task: {task_id}")
            ids = json.loads(row["pmc_ids"] or "[]")
            size = int(row["batch_size"] or self.default_batch_size)
        finally:
            conn.close()

        self._run(task_id, ids, size)
        return self.status(task_id)

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
                        embedded = _call_with_timeout(
                            lambda: self._embed_batch(parsed), self.batch_timeout
                        )
                    except TimeoutError:
                        for item in parsed:
                            failures.append(
                                {"pmc_id": item["pmc_id"], "error": "embed: timeout"}
                            )
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
                path = self._download_with_retry(pmc_id)
                if not path:
                    failures.append(
                        {
                            "pmc_id": pmc_id,
                            "error": f"download failed after {self.download_retries} attempts",
                        }
                    )
                    continue
                data = (self._parse or self._default_parse)(path)
                if not data or not data.get("title"):
                    failures.append({"pmc_id": pmc_id, "error": "no title"})
                    continue
                parsed.append({"pmc_id": pmc_id, "data": data})
            except Exception as exc:  # noqa: BLE001 - one bad paper must not kill the batch
                failures.append({"pmc_id": pmc_id, "error": str(exc)[:200]})
        return parsed

    def _download_with_retry(self, pmc_id: str) -> Path | None:
        """Retry transient download failures with a small backoff."""
        downloader = self._download or self._default_download
        for attempt in range(1, self.download_retries + 1):
            try:
                path = downloader(pmc_id)
                if path:
                    return path
            except Exception as exc:  # noqa: BLE001 - retried below
                self.log(f"download {pmc_id} attempt {attempt} failed: {exc}")
            if attempt < self.download_retries:
                time.sleep(self.download_retry_delay * attempt)
        return None

    def _write_batch(self, conn: sqlite3.Connection, parsed: Sequence[Mapping[str, Any]]) -> int:
        written = 0
        # `paragraphs_ad` deletes from FTS5 with `WHERE para_id = ?`, which is a
        # full scan per deleted row (para_id is UNINDEXED). Dropping it for the
        # batch and deleting by a single set-based join keeps re-ingest fast.
        has_fts = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paragraphs_fts'"
        ).fetchone() is not None
        has_sentences = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sentences'"
        ).fetchone() is not None
        paper_cols = {row[1] for row in conn.execute("PRAGMA table_info(papers)")}
        if has_fts:
            conn.execute("DROP TRIGGER IF EXISTS paragraphs_ad")
        try:
            with conn:  # BEGIN ... COMMIT; any exception rolls the whole batch back
                for item in parsed:
                    data = item["data"]
                    paper_id = _paper_id(item["pmc_id"])
                    if has_fts:
                        # REPLACE does not fire DELETE triggers by default, so the
                        # old papers_fts row must be removed explicitly.
                        conn.execute(
                            "DELETE FROM papers_fts WHERE paper_id = ?", (paper_id,)
                        )
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
                    if {"journal", "year", "doi"} <= paper_cols:
                        conn.execute(
                            "UPDATE papers SET journal = ?, year = ?, doi = ? WHERE paper_id = ?",
                            (
                                data.get("journal") or "",
                                data.get("year"),
                                data.get("doi") or "",
                                paper_id,
                            ),
                        )
                    if has_fts:
                        conn.execute(
                            "DELETE FROM paragraphs_fts WHERE para_id IN "
                            "(SELECT para_id FROM paragraphs WHERE paper_id = ?)",
                            (paper_id,),
                        )
                    conn.execute("DELETE FROM sentences WHERE paper_id = ?", (paper_id,)) if has_sentences else None
                    conn.execute("DELETE FROM paragraphs WHERE paper_id = ?", (paper_id,))
                    from build_db.sentence_geometry import split_sentences

                    for index, para in enumerate(data.get("paragraphs") or []):
                        para_id = f"{paper_id}_para_{index:05d}"
                        path = para.get("path") or []
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO paragraphs
                            (para_id, paper_id, section_level1, text, sequence, parse_engine)
                            VALUES (?, ?, ?, ?, ?, 'xml')
                            """,
                            (
                                para_id,
                                paper_id,
                                (path[0] if path else para.get("section")) or "",
                                para.get("text") or "",
                                para.get("sequence") or index,
                            ),
                        )
                        for sent_index, text in enumerate(split_sentences(para.get("text") or "")):
                            if not has_sentences:
                                break
                            conn.execute(
                                "INSERT OR REPLACE INTO sentences "
                                "(sentence_id, para_id, paper_id, text, sequence, section_id) "
                                "VALUES (?, ?, ?, ?, ?, NULL)",
                                (
                                    f"{para_id}_sent_{sent_index:03d}",
                                    para_id,
                                    paper_id,
                                    text,
                                    sent_index,
                                ),
                            )
                    written += 1
        finally:
            if has_fts:
                conn.execute(
                    """
                    CREATE TRIGGER IF NOT EXISTS paragraphs_ad AFTER DELETE ON paragraphs BEGIN
                      DELETE FROM paragraphs_fts WHERE para_id = old.para_id;
                    END
                    """
                )
                conn.commit()
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
        embedder = self._embed_client or self._embed or self._default_embed
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
        from build_db.import_jats import parse_file

        data = parse_file(path)
        metadata = data.get("metadata") or {}
        return {
            **metadata,
            "abstract": metadata.get("abstract") or "",
            "authors": "; ".join(metadata.get("authors") or []),
            "paragraphs": data.get("paragraphs") or [],
            "sections": data.get("sections") or [],
            "figures": data.get("figures") or [],
            "tables": data.get("tables") or [],
            "references": data.get("references") or [],
        }

    def _default_embed(self, rows: Sequence[Mapping[str, Any]]) -> int:
        if not self.chroma_path:
            return 0
        import chromadb
        from sentence_transformers import SentenceTransformer

        model_path = Path(r"D:\models\models\BAAI--bge-base-en-v1.5")
        model = getattr(self, "_model", None)
        if model is None:
            # Default to CPU: worker + Flask both load models, and two CUDA
            # contexts on one GPU made ingest stall indefinitely.
            device = os.environ.get("SCIPAL_INGEST_DEVICE", "cpu").strip() or "cpu"
            model = SentenceTransformer(str(model_path), device=device)
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


def _call_with_timeout(func: Callable[[], Any], timeout: float) -> Any:
    """Run ``func`` in a daemon thread; raise TimeoutError if it overruns.

    A hung Chroma/embedding call cannot be cancelled, but the batch is marked
    failed instead of blocking the whole task forever.
    """
    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = func()
        except BaseException as exc:  # noqa: BLE001 - re-raised in caller
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"batch exceeded {timeout:.0f}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")
