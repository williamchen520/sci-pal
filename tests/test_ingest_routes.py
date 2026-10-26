"""Route tests for the async ingest endpoints."""

from __future__ import annotations

import unittest

from flask import Flask

from routes.ingest import build_ingest_blueprint


class FakeService:
    def __init__(self) -> None:
        self.tasks = {}

    def start(self, pmc_ids, *, batch_size=None):
        if not pmc_ids:
            raise ValueError("pmc_ids must not be empty")
        task_id = "ing_test"
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "total": len(pmc_ids),
            "batch_size": batch_size or 5,
        }
        return task_id

    def status(self, task_id):
        return self.tasks.get(task_id)

    def cancel(self, task_id):
        if task_id not in self.tasks:
            return False
        self.tasks[task_id]["status"] = "cancelled"
        return True


def make_app(service):
    app = Flask(__name__)
    app.register_blueprint(build_ingest_blueprint(get_service=lambda: service, log=app.logger))
    return app


class IngestRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FakeService()
        self.client = make_app(self.service).test_client()

    def test_submit_returns_202_and_task_id(self) -> None:
        resp = self.client.post("/api/ingest", json={"pmc_ids": ["PMC1", "PMC2"], "batch_size": 5})
        self.assertEqual(resp.status_code, 202)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["task_id"], "ing_test")

    def test_empty_ids_rejected(self) -> None:
        resp = self.client.post("/api/ingest", json={"pmc_ids": []})
        self.assertEqual(resp.status_code, 400)

    def test_status_unknown_returns_404(self) -> None:
        resp = self.client.get("/api/ingest/ing_missing")
        self.assertEqual(resp.status_code, 404)

    def test_cancel_and_status(self) -> None:
        self.client.post("/api/ingest", json={"pmc_ids": ["PMC1"]})
        self.assertEqual(self.client.post("/api/ingest/ing_test/cancel").status_code, 200)
        body = self.client.get("/api/ingest/ing_test").get_json()
        self.assertEqual(body["task"]["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
