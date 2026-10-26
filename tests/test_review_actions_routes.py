"""Review action routes moved to routes/review_actions.py (outline/saved/assign/generate)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from routes.review_actions import build_review_actions_blueprint


class FakeTaskManager:
    def __init__(self):
        self.created = []
        self.failed = []
        self.completed = []

    def create_task(self, kind):
        task_id = f"t{len(self.created) + 1}"
        self.created.append((kind, task_id))
        return task_id

    def fail_task(self, task_id, reason):
        self.failed.append((task_id, reason))

    def complete_task(self, task_id, result):
        self.completed.append((task_id, result))

    def cancel_task(self, task_id):
        return True

    def get_task(self, task_id):
        return {"id": task_id}

    def get_running_task(self):
        return None


class FakeLLM:
    provider = "ollama"
    model = "qwen2.5:3b"

    def __init__(self, available=False):
        self.available = available

    def is_available(self):
        return self.available

    def list_models(self):
        return []


class FakeOutlineStore:
    def __init__(self):
        self.records = {}

    def list(self):
        return list(self.records.values())

    def load(self, name):
        return self.records.get(name)

    def save(self, name, topic, outline_data, review_type, paper_count):
        record = {
            "name": name,
            "topic": topic,
            "outline": outline_data,
            "review_type": review_type,
            "paper_count": paper_count,
            "updated_at": "2026-10-27T00:00:00Z",
        }
        self.records[name] = record
        return record

    def delete(self, name):
        return self.records.pop(name, None) is not None


OUTLINE = {"sections": [{"title": "Intro", "paragraphs": []}]}
PAPERS = [{"paper_id": "p1", "title": "T"}]


def make_app(available=False):
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    app = Flask(__name__)
    store = FakeOutlineStore()
    app.register_blueprint(
        build_review_actions_blueprint(
            get_task_manager=lambda: FakeTaskManager(),
            get_llm_client=lambda: FakeLLM(available=available),
            get_review_generator=lambda: None,
            get_review_store=lambda: None,
            get_outline_store=lambda: store,
            get_retriever=lambda: object(),
            db_path=Path(tmp.name) / "research.db",
            log=app.logger,
        )
    )
    app.config["TMP"] = tmp
    return app


class ReviewActionRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = make_app()
        self.client = self.app.test_client()

    def test_all_nine_rules_registered(self) -> None:
        rules = {
            rule.rule
            for rule in self.app.url_map.iter_rules()
            if rule.rule.startswith("/api/review")
        }
        for path in (
            "/api/review/outline",
            "/api/review/assign_papers",
            "/api/review/search_and_assign",
            "/api/review/outline/saved",
            "/api/review/outline/saved/<name>",
            "/api/review/outline/save",
            "/api/review/generate",
            "/api/review/generate_async",
        ):
            self.assertIn(path, rules)

    def test_outline_requires_topic(self) -> None:
        self.assertEqual(self.client.post("/api/review/outline", json={}).status_code, 400)

    def test_outline_returns_task_id(self) -> None:
        response = self.client.post("/api/review/outline", json={"topic": "sepsis"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("task_id", response.get_json())

    def test_saved_outline_crud(self) -> None:
        saved = self.client.post(
            "/api/review/outline/save",
            json={"name": "o1", "topic": "t", "outline": OUTLINE},
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get("/api/review/outline/saved").get_json()["count"], 1)
        self.assertEqual(self.client.get("/api/review/outline/saved/o1").status_code, 200)
        self.assertEqual(self.client.delete("/api/review/outline/saved/o1").status_code, 200)
        self.assertEqual(self.client.get("/api/review/outline/saved/o1").status_code, 404)

    def test_assign_papers(self) -> None:
        with patch(
            "services.review.review_generator.assign_papers_to_outline",
            return_value={"sections": [{"title": "Intro", "assigned_paper_ids": ["p1"]}]},
        ):
            response = self.client.post(
                "/api/review/assign_papers", json={"outline": OUTLINE, "papers": PAPERS}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("outline", response.get_json())

    def test_search_and_assign(self) -> None:
        with patch(
            "services.review.review_generator.search_and_assign_papers",
            return_value=(OUTLINE, PAPERS),
        ):
            response = self.client.post(
                "/api/review/search_and_assign",
                json={"outline": OUTLINE, "topic": "sepsis", "max_papers": 1},
            )
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["papers"][0]["paper_id"], "p1")

    def test_generate_returns_503_without_llm(self) -> None:
        response = self.client.post("/api/review/generate", json={"topic": "sepsis"})
        self.assertEqual(response.status_code, 503)

    def test_generate_async_returns_task_id(self) -> None:
        response = self.client.post("/api/review/generate_async", json={"topic": "sepsis"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("task_id", response.get_json())


if __name__ == "__main__":
    unittest.main()
