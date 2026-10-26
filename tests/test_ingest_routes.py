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


def make_app(service, embed_rows=None):
    app = Flask(__name__)
    app.register_blueprint(
        build_ingest_blueprint(
            get_service=lambda: service, log=app.logger, embed_rows=embed_rows
        )
    )
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


    def test_embed_bridge_writes_through_callback(self) -> None:
        seen = []

        def embed_rows(rows):
            seen.extend(rows)
            return len(rows)

        client = make_app(self.service, embed_rows=embed_rows).test_client()
        resp = client.post("/api/embed", json={"rows": [{"para_id": "p1", "text": "x"}]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["count"], 1)
        self.assertEqual(seen[0]["para_id"], "p1")

    def test_embed_disabled_returns_503(self) -> None:
        resp = self.client.post("/api/embed", json={"rows": [{"para_id": "p1"}]})
        self.assertEqual(resp.status_code, 503)


if __name__ == "__main__":
    unittest.main()
