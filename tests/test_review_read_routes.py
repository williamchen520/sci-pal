"""Review task/store/LLM routes moved out of api_server."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.reviews import build_reviews_blueprint


class FakeTaskManager:
    def __init__(self):
        self.tasks = {"t1": {"id": "t1", "status": "running"}}
        self.running = {"id": "t1", "status": "running"}

    def get_running_task(self):
        return self.running

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def cancel_task(self, task_id):
        return task_id in self.tasks


class FakeStore:
    def get(self, review_id):
        return {"review_id": review_id, "markdown": "#"} if review_id == "r1" else None

    def get_sentence(self, review_id, sentence_id):
        return {"sentence_id": sentence_id} if review_id == "r1" else None


class FakeLLM:
    provider = "ollama"
    model = "qwen2.5:3b"

    def is_available(self):
        return True

    def list_models(self):
        return ["qwen2.5:3b"]


def make_app(with_deps: bool = True):
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    app = Flask(__name__)
    app.register_blueprint(
        build_reviews_blueprint(
            db_path=Path(tmp.name) / "r.db",
            log=app.logger,
            get_task_manager=(lambda: FakeTaskManager()) if with_deps else None,
            get_review_store=(lambda: FakeStore()) if with_deps else None,
            get_llm_client=(lambda: FakeLLM()) if with_deps else None,
        )
    )
    app.config["TMP"] = tmp
    return app


class ReviewReadRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = make_app()
        self.client = self.app.test_client()

    def test_running_task(self) -> None:
        body = self.client.get("/api/review/running_task").get_json()
        self.assertTrue(body["running"])
        self.assertEqual(body["task"]["id"], "t1")

    def test_task_status_and_404(self) -> None:
        self.assertEqual(self.client.get("/api/review/task/t1").get_json()["id"], "t1")
        self.assertEqual(self.client.get("/api/review/task/nope").status_code, 404)

    def test_cancel(self) -> None:
        self.assertEqual(self.client.post("/api/review/cancel/t1").status_code, 200)
        self.assertEqual(self.client.post("/api/review/cancel/nope").status_code, 404)

    def test_review_detail_and_sentence(self) -> None:
        self.assertEqual(self.client.get("/api/review/r1").get_json()["review_id"], "r1")
        self.assertEqual(self.client.get("/api/review/r1/sentence/s1").get_json()["sentence_id"], "s1")
        self.assertEqual(self.client.get("/api/review/nope").status_code, 404)

    def test_llm_status(self) -> None:
        body = self.client.get("/api/review/llm_status").get_json()
        self.assertTrue(body["data"]["available"])
        self.assertEqual(body["data"]["provider"], "ollama")

    def test_without_deps_returns_safe_responses(self) -> None:
        client = make_app(with_deps=False).test_client()
        self.assertFalse(client.get("/api/review/running_task").get_json()["running"])
        self.assertEqual(client.get("/api/review/task/t1").status_code, 404)
        self.assertEqual(client.get("/api/review/llm_status").status_code, 500)


if __name__ == "__main__":
    unittest.main()
