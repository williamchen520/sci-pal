"""Tests for the extracted download-status blueprint."""

from __future__ import annotations

import unittest

from flask import Flask

from routes.search import build_search_blueprint


class FakeTask:
    def __init__(self, task_id: str, status: str = "running") -> None:
        self.task_id = task_id
        self.status = status

    def to_dict(self):
        return {"task_id": self.task_id, "status": self.status}


class FakeManager:
    def __init__(self, tasks=None, current=None, error=None) -> None:
        self.tasks = tasks or {}
        self.current = current
        self.error = error
        self.limit_seen = None

    def get_task(self, task_id):
        if self.error:
            raise self.error
        return self.tasks.get(task_id)

    def list_tasks(self, limit=20):
        if self.error:
            raise self.error
        self.limit_seen = limit
        return [task.to_dict() for task in self.tasks.values()]

    def get_queue_status(self):
        if self.error:
            raise self.error
        return {
            "current_task_id": self.current,
            "queue_length": 0,
            "queued_task_ids": [],
        }


def make_app(manager) -> Flask:
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(
        build_search_blueprint(get_task_manager=lambda: manager, log=app.logger)
    )
    return app


class DownloadStatusTests(unittest.TestCase):
    def test_missing_task_id(self) -> None:
        resp = make_app(FakeManager()).test_client().get("/api/search/download_status")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("task_id", resp.get_json()["error"])

    def test_unknown_task(self) -> None:
        resp = make_app(FakeManager()).test_client().get(
            "/api/search/download_status?task_id=dl_x"
        )
        self.assertEqual(resp.status_code, 404)

    def test_found_task(self) -> None:
        manager = FakeManager({"dl_1": FakeTask("dl_1", "completed")})
        resp = make_app(manager).test_client().get("/api/search/download_status?task_id=dl_1")
        self.assertEqual(resp.get_json(), {"task_id": "dl_1", "status": "completed"})

    def test_manager_error_is_500_without_leaking(self) -> None:
        manager = FakeManager(error=RuntimeError("secret disk path"))
        resp = make_app(manager).test_client().get("/api/search/download_status?task_id=dl_1")
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("secret", resp.get_json()["error"])


class DownloadHistoryTests(unittest.TestCase):
    def test_history_shape(self) -> None:
        manager = FakeManager({"dl_1": FakeTask("dl_1")})
        resp = make_app(manager).test_client().get("/api/search/download_history")
        body = resp.get_json()
        self.assertEqual(body["total"], 1)
        self.assertIn("queue_status", body)
        self.assertEqual(manager.limit_seen, 20)

    def test_limit_is_capped(self) -> None:
        manager = FakeManager()
        make_app(manager).test_client().get("/api/search/download_history?limit=500")
        self.assertEqual(manager.limit_seen, 50)


class DownloadQueueTests(unittest.TestCase):
    def test_queue_without_current(self) -> None:
        resp = make_app(FakeManager()).test_client().get("/api/search/download_queue")
        body = resp.get_json()
        self.assertIsNone(body["current_task"])
        self.assertEqual(body["queue_length"], 0)

    def test_queue_with_current(self) -> None:
        manager = FakeManager({"dl_1": FakeTask("dl_1")}, current="dl_1")
        resp = make_app(manager).test_client().get("/api/search/download_queue")
        self.assertEqual(resp.get_json()["current_task"]["task_id"], "dl_1")


if __name__ == "__main__":
    unittest.main()
