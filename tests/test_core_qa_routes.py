"""Core (health/retrieve) and QA/agentic blueprints."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from routes.core import build_core_blueprint
from routes.qa import build_qa_blueprint


class FakeRetriever:
    def retrieve(self, **kwargs):
        return {"query": kwargs["query"], "paragraphs": [{"id": "p1"}]}


class FakeQA:
    def ask(self, question, paper_id=None, include_diagnostics=False):
        return {"answer": f"answer to {question}"}

    def get_llm_status(self):
        return {"available": True, "provider": "ollama"}


class FakeTaskManager:
    def __init__(self):
        self.tasks = {}

    def create_task(self, kind):
        task_id = f"t{len(self.tasks) + 1}"
        self.tasks[task_id] = kind
        return task_id

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


def make_app():
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    app = Flask(__name__)
    app.register_blueprint(
        build_core_blueprint(db_path=Path(tmp.name) / "x.db", get_retriever=lambda: FakeRetriever())
    )
    app.register_blueprint(
        build_qa_blueprint(
            get_qa_service=lambda: FakeQA(),
            get_retriever=lambda: FakeRetriever(),
            get_task_manager=lambda: FakeTaskManager(),
        )
    )
    app.config["TMP"] = tmp
    return app


class CoreAndQaRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_app().test_client()

    def test_health(self) -> None:
        body = self.client.get("/api/health").get_json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("db_exists", body)

    def test_retrieve_requires_q(self) -> None:
        self.assertEqual(self.client.post("/api/retrieve", json={}).status_code, 400)

    def test_retrieve_returns_result(self) -> None:
        body = self.client.post("/api/retrieve", json={"q": "sepsis"}).get_json()
        self.assertEqual(body["query"], "sepsis")

    def test_qa_ask(self) -> None:
        response = self.client.post("/api/qa/ask", json={"question": "what?"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("answer", response.get_json())

    def test_qa_ask_requires_question(self) -> None:
        self.assertEqual(self.client.post("/api/qa/ask", json={}).status_code, 400)

    def test_qa_status(self) -> None:
        body = self.client.get("/api/qa/status").get_json()
        self.assertTrue(body["available"])

    def test_qa_ask_async_returns_task_id(self) -> None:
        response = self.client.post("/api/qa/ask_async", json={"question": "what?"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("task_id", response.get_json())

    def test_agentic_search(self) -> None:
        class FakeAgentic:
            def __init__(self, **kwargs):
                pass

            def search(self, q, paper_id=None, top_paragraphs=6):
                return {"query": q, "entities": []}

        with patch("services.search.agentic_search.AgenticSearcher", FakeAgentic):
            response = self.client.post("/api/agentic/search", json={"q": "sepsis"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["query"], "sepsis")

    def test_agentic_requires_q(self) -> None:
        self.assertEqual(self.client.post("/api/agentic/search", json={}).status_code, 400)

    def test_agentic_async_returns_task_id(self) -> None:
        class FakeAgentic:
            def __init__(self, **kwargs):
                pass

            def search(self, q, paper_id=None, top_paragraphs=6):
                return {"query": q, "entities": []}

        # the endpoint runs a daemon thread; unpachted it imports the real
        # searcher and keeps running while later tests execute (slow suite)
        with patch("services.search.agentic_search.AgenticSearcher", FakeAgentic):
            response = self.client.post("/api/agentic/search_async", json={"q": "sepsis"})
            self.assertEqual(response.status_code, 200)
            self.assertIn("task_id", response.get_json())
            time.sleep(0.05)


if __name__ == "__main__":
    unittest.main()
