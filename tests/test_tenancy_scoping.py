"""Workspace filtering for retrieval results and QA routes."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.qa import build_qa_blueprint
from services.tenancy import create_user, create_workspace
from services.tenancy.scoping import allowed_paper_ids, filter_retrieval_result


class FakeQA:
    def ask(self, question, paper_id=None, include_diagnostics=False, workspace_id=None, **kwargs):
        return {"answer": f"answer to {question}", "paper_id": paper_id, "workspace_id": workspace_id}


class FakeTasks:
    def create_task(self, kind):
        return "t1"


class ScopingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "scoping.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, workspace_id TEXT)")
        conn.execute("INSERT INTO papers VALUES ('p_a', 'ws_a')")
        conn.execute("INSERT INTO papers VALUES ('p_b', 'ws_b')")
        conn.commit()
        conn.close()

    def test_allowed_ids(self) -> None:
        self.assertEqual(allowed_paper_ids("ws_a", db_path=self.db), {"p_a"})
        self.assertEqual(filter_retrieval_result(
            {
                "paragraphs": [
                    {"paper_id": "p_a", "text": "keep"},
                    {"paper_id": "p_b", "text": "drop"},
                ],
                "papers": [{"paper_id": "p_a"}, {"paper_id": "p_b"}],
                "figures": [{"paper_id": "p_b", "caption": "drop"}],
            },
            {"p_a"},
        )["paragraphs"], [{"paper_id": "p_a", "text": "keep"}])

    def test_filter_keeps_unknown_shape(self) -> None:
        result = filter_retrieval_result(
            {"paragraphs": [{"metadata": {"paper_id": "p_a"}, "text": "x"}]},
            {"p_a"},
        )
        self.assertEqual(len(result["paragraphs"]), 1)


class QAScopingRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "qa.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, workspace_id TEXT)")
        conn.commit()
        conn.close()
        self.user = create_user("alice", "long-enough-password", db_path=self.db)
        self.ws = create_workspace("A", self.user["user_id"], db_path=self.db)["workspace_id"]
        self.other = create_user("bob", "long-enough-password", db_path=self.db)
        other_ws = create_workspace("B", self.other["user_id"], db_path=self.db)["workspace_id"]
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO papers VALUES ('p_a', ?)", (self.ws,))
        conn.execute("INSERT INTO papers VALUES ('p_b', ?)", (other_ws,))
        conn.commit()
        conn.close()
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(
            build_qa_blueprint(
                get_qa_service=lambda: FakeQA(),
                get_retriever=lambda: None,
                get_task_manager=lambda: FakeTasks(),
                db_path=str(self.db),
            )
        )
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user["user_id"]
            session["workspace_id"] = self.ws

    def test_cross_workspace_paper_rejected(self) -> None:
        response = self.client.post("/api/qa/ask", json={"question": "q", "paper_id": "p_b"})
        self.assertEqual(response.status_code, 404)

    def test_own_workspace_paper_allowed(self) -> None:
        response = self.client.post("/api/qa/ask", json={"question": "q", "paper_id": "p_a"})
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
