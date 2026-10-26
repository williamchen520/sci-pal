"""Tests for the extracted task routes."""

from __future__ import annotations

import unittest

from flask import Flask

from routes.tasks import build_tasks_blueprint


def make_app(*, tasks=None, task=None, events=None):
    tasks = tasks if tasks is not None else []
    app = Flask(__name__)
    app.register_blueprint(
        build_tasks_blueprint(
            list_tasks=lambda **kwargs: tasks,
            get_task=lambda task_id: task,
            subscribe=lambda task_id: iter(events or []),
        )
    )
    return app


class TaskRoutesTests(unittest.TestCase):
    def test_list_returns_tasks_and_count(self) -> None:
        client = make_app(tasks=[{"task_id": "a"}, {"task_id": "b"}]).test_client()
        body = client.get("/api/tasks?limit=10").get_json()
        self.assertEqual(body["count"], 2)

    def test_detail_unknown_returns_404(self) -> None:
        self.assertEqual(make_app(task=None).test_client().get("/api/tasks/x").status_code, 404)

    def test_detail_returns_task(self) -> None:
        response = make_app(task={"task_id": "x", "status": "done"}).test_client().get("/api/tasks/x")
        self.assertEqual(response.get_json()["status"], "done")

    def test_events_stream_is_sse(self) -> None:
        response = make_app(events=[("progress", {"task_id": "x", "percent": 10})]).test_client().get(
            "/api/tasks/x/events"
        )
        self.assertIn("text/event-stream", response.headers["Content-Type"])
        self.assertIn(b"event: progress", response.data)


if __name__ == "__main__":
    unittest.main()
