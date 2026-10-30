"""Workspace isolation for paper read routes."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.papers import build_papers_blueprint
from services.tenancy import create_user, create_workspace


class PaperIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "papers.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, "
            "journal TEXT, year INTEGER, doi TEXT, abstract TEXT, workspace_id TEXT, "
            "total_paragraphs INTEGER DEFAULT 0, total_figures INTEGER DEFAULT 0, "
            "total_tables INTEGER DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE cross_paper_index (source_paper_id TEXT, target_paper_id TEXT, "
            "relation TEXT, confidence REAL)"
        )
        conn.commit()
        conn.close()

        self.user_a = create_user("alice", "long-enough-password", db_path=self.db)
        self.user_b = create_user("bob", "long-enough-password", db_path=self.db)
        self.ws_a = create_workspace("Lab A", self.user_a["user_id"], db_path=self.db)["workspace_id"]
        self.ws_b = create_workspace("Lab B", self.user_b["user_id"], db_path=self.db)["workspace_id"]

        conn = sqlite3.connect(self.db)
        conn.execute(
            "INSERT INTO papers (paper_id, title, year, workspace_id) VALUES ('p_a', 'A paper', 2026, ?)",
            (self.ws_a,),
        )
        conn.execute(
            "INSERT INTO papers (paper_id, title, year, workspace_id) VALUES ('p_b', 'B paper', 2026, ?)",
            (self.ws_b,),
        )
        conn.commit()
        conn.close()

        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.register_blueprint(
            build_papers_blueprint(
                db_path=self.db,
                get_graph=lambda: None,
                log=app.logger,
            )
        )
        self.client = app.test_client()

    def login(self, user: dict, workspace_id: str) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = workspace_id

    def test_user_sees_only_own_workspace(self) -> None:
        self.login(self.user_a, self.ws_a)
        body = self.client.get("/api/papers").get_json()
        self.assertEqual([item["paper_id"] for item in body["papers"]], ["p_a"])
        self.assertTrue(all(item["workspace_id"] == self.ws_a for item in body["papers"]))

    def test_cross_workspace_detail_is_404(self) -> None:
        self.login(self.user_a, self.ws_a)
        self.assertEqual(self.client.get("/api/papers/p_a").status_code, 200)
        self.assertEqual(self.client.get("/api/papers/p_b").status_code, 404)

    def test_other_user_sees_own_workspace(self) -> None:
        self.login(self.user_b, self.ws_b)
        body = self.client.get("/api/papers").get_json()
        self.assertEqual([item["paper_id"] for item in body["papers"]], ["p_b"])

    def test_auth_required_rejects_anonymous(self) -> None:
        previous = os.environ.get("SCIPAL_AUTH_REQUIRED")
        os.environ["SCIPAL_AUTH_REQUIRED"] = "1"
        try:
            self.assertEqual(self.client.get("/api/papers").status_code, 401)
        finally:
            if previous is None:
                os.environ.pop("SCIPAL_AUTH_REQUIRED", None)
            else:
                os.environ["SCIPAL_AUTH_REQUIRED"] = previous


if __name__ == "__main__":
    unittest.main()
