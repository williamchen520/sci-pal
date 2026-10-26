"""Tests for the batch download + vectorise service."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from services.search.ingest import IngestService


class Boom:
    """Iterable that explodes: simulates a corrupt parse writing bad paragraphs."""

    def __iter__(self):
        raise RuntimeError("boom")


def wait_for(service: IngestService, task_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = service.status(task_id)
        if task and task["status"] in {"completed", "partial", "failed", "cancelled"}:
            return task
        time.sleep(0.02)
    return service.status(task_id) or {}


class IngestServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "research.db"
        self.ids = [f"PMC{index:06d}" for index in range(1, 11)]

        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY, filename TEXT, title TEXT, abstract TEXT,
                authors TEXT, parse_engine TEXT
            );
            CREATE TABLE paragraphs (
                para_id TEXT PRIMARY KEY, paper_id TEXT, section_level1 TEXT,
                text TEXT, sequence INTEGER, parse_engine TEXT
            );
            """
        )
        conn.commit()
        conn.close()

    def _service(self, *, batch_size=5, bad_paper=None, embed=None, delay=0.0) -> IngestService:
        def download(pmc_id: str) -> Path:
            if delay:
                time.sleep(delay)
            return self.root / f"{pmc_id}.xml"

        def parse(path: Path):
            pmc_id = path.stem
            if bad_paper and pmc_id == bad_paper:
                return {"title": "bad", "abstract": "", "authors": "", "paragraphs": Boom()}
            return {
                "title": f"Title {pmc_id}",
                "abstract": "abstract",
                "authors": "A, B",
                "paragraphs": [
                    {"section": "Intro", "text": f"body {pmc_id}", "sequence": 0},
                    {"section": "Intro", "text": f"more {pmc_id}", "sequence": 1},
                ],
            }

        def default_embed(rows) -> int:
            return len(rows)

        return IngestService(
            db_path=self.db,
            xml_dir=self.root,
            batch_size=batch_size,
            download=download,
            parse=parse,
            embed=embed or default_embed,
            log=lambda _: None,
        )

    def test_batches_commit_independently_and_finish(self) -> None:
        service = self._service(batch_size=5)
        task_id = service.start(self.ids, batch_size=5)
        task = wait_for(service, task_id)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["processed"], 10)
        self.assertEqual(task["imported"], 10)

        conn = sqlite3.connect(self.db)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 10)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM paragraphs").fetchone()[0], 20)
        conn.close()

    def test_broken_batch_rolls_back_only_itself(self) -> None:
        service = self._service(batch_size=5, bad_paper="PMC000007")
        task_id = service.start(self.ids, batch_size=5)
        task = wait_for(service, task_id)
        self.assertEqual(task["status"], "partial")
        self.assertEqual(task["imported"], 5)

        conn = sqlite3.connect(self.db)
        remaining = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 5)

        failures = json.loads(task["error"])
        self.assertTrue(any(item["pmc_id"] == "PMC000007" for item in failures))

    def test_wal_mode_is_enabled(self) -> None:
        service = self._service()
        conn = service._connect()
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(mode.lower(), "wal")

    def test_cancel_stops_between_batches(self) -> None:
        service = self._service(batch_size=2, delay=0.05)
        task_id = service.start(self.ids, batch_size=2)
        time.sleep(0.12)
        self.assertTrue(service.cancel(task_id))
        task = wait_for(service, task_id)
        self.assertEqual(task["status"], "cancelled")

    def test_queue_mode_writes_job_instead_of_thread(self) -> None:
        service = self._service()
        service.queue_dir = self.root / "queue"
        task_id = service.start(self.ids[:2], batch_size=2)
        task = service.status(task_id)
        self.assertEqual(task["status"], "queued")
        jobs = list((self.root / "queue").glob("ingest-*.job.json"))
        self.assertEqual(len(jobs), 1)
        payload = json.loads(jobs[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["type"], "ingest")
        self.assertEqual(payload["task_id"], task_id)

    def test_execute_runs_queued_task(self) -> None:
        service = self._service()
        service.queue_dir = self.root / "queue"
        task_id = service.start(self.ids[:4], batch_size=2)
        task = service.execute(task_id)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["imported"], 4)

    def test_embed_client_is_used_instead_of_local_model(self) -> None:
        seen = []

        def embed_client(rows):
            seen.append(len(rows))
            return len(rows)

        service = IngestService(
            db_path=self.db,
            xml_dir=self.root,
            download=lambda pmc_id: self.root / f"{pmc_id}.xml",
            parse=lambda path: {
                "title": path.stem,
                "abstract": "",
                "authors": "",
                "paragraphs": [{"section": "Intro", "text": "body", "sequence": 0}],
            },
            embed_client=embed_client,
            log=lambda _: None,
        )
        task_id = service.start(self.ids[:2], batch_size=2)
        task = wait_for(service, task_id)
        self.assertEqual(task["status"], "completed")
        self.assertTrue(seen)

    def test_embed_timeout_marks_failure(self) -> None:
        import time as _time

        def slow_embed(rows):
            _time.sleep(1.0)
            return len(rows)

        service = IngestService(
            db_path=self.db,
            xml_dir=self.root,
            download=lambda pmc_id: self.root / f"{pmc_id}.xml",
            parse=lambda path: {
                "title": path.stem,
                "abstract": "",
                "authors": "",
                "paragraphs": [{"section": "Intro", "text": "body", "sequence": 0}],
            },
            embed_client=slow_embed,
            batch_timeout=0.2,
            log=lambda _: None,
        )
        task_id = service.start(self.ids[:1], batch_size=1)
        task = wait_for(service, task_id)
        self.assertIn(task["status"], {"partial", "failed"})
        self.assertIn("timeout", task["error"] or "")

    def test_unknown_task_returns_none(self) -> None:
        self.assertIsNone(self._service().status("ing_missing"))


if __name__ == "__main__":
    unittest.main()
