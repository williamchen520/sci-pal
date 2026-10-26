"""Papers and online-download blueprints (route level)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.papers_actions import build_papers_actions_blueprint
from routes.search_downloads import build_search_downloads_blueprint


class FakeTaskManager:
    def create_task(self, kind):
        return "t1"

    def is_cancelled(self, task_id):
        return False

    def cancel_task(self, task_id):
        return True

    def update_progress(self, task_id, message):
        pass

    def complete_task(self, task_id, result):
        pass

    def fail_task(self, task_id, reason):
        pass


def make_app(root: Path, db: Path):
    app = Flask(__name__)
    app.register_blueprint(
        build_papers_actions_blueprint(
            db_path=db,
            project_root=root,
            get_task_manager=lambda: FakeTaskManager(),
            log=app.logger,
        )
    )
    app.register_blueprint(
        build_search_downloads_blueprint(
            db_path=db,
            project_root=root,
            get_task_manager=lambda: FakeTaskManager(),
            log=app.logger,
        )
    )
    return app


class PapersDownloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "documents").mkdir()
        (self.root / "documents" / "a.pdf").write_bytes(b"%PDF-1.4")
        self.db = self.root / "research.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT, filename TEXT, title TEXT, authors TEXT, "
            "year INTEGER, total_paragraphs INTEGER)"
        )
        conn.execute(
            "INSERT INTO papers VALUES ('p1', 'a.pdf', 'Paper A', 'X', 2026, 10)"
        )
        conn.commit()
        conn.close()
        self.client = make_app(self.root, self.db).test_client()

    def test_local_lists_pdfs_with_parse_state(self) -> None:
        body = self.client.get("/api/papers/local").get_json()
        self.assertEqual(body["total"], 1)
        self.assertTrue(body["papers"][0]["parsed"])
        self.assertEqual(body["papers"][0]["paper_id"], "p1")

    def test_pdf_missing_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/papers/nope/pdf").status_code, 404)

    def test_import_without_file_returns_400(self) -> None:
        self.assertEqual(self.client.post("/api/papers/import", data={}).status_code, 400)

    def test_download_online_requires_pmc_ids(self) -> None:
        self.assertEqual(
            self.client.post("/api/search/download_online", json={}).status_code, 400
        )

    def test_retry_unknown_task_returns_error(self) -> None:
        response = self.client.post("/api/search/retry_download", json={"task_id": "nope"})
        self.assertIn(response.status_code, (400, 404))

    def test_annotations_unknown_paper_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/papers/nope/annotations").status_code, 404)

    def test_annotate_unknown_paper_returns_404(self) -> None:
        response = self.client.post(
            "/api/papers/nope/annotate",
            json={"page": 1, "type": "highlight", "rect": [0, 0, 1, 1]},
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
