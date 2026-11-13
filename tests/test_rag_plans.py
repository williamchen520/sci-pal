"""R1 plan/job tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint
from services.rag_control.plans import _plan_hash


class PlanHashTests(unittest.TestCase):
    def test_hash_is_stable_and_sensitive(self) -> None:
        steps = [{"action": "rag_query", "rag_id": "code"}]
        self.assertEqual(_plan_hash("x", steps), _plan_hash("x", steps))
        self.assertNotEqual(_plan_hash("x", steps), _plan_hash("y", steps))


class PlanRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_approval_rejects_internal_agent_token(self) -> None:
        response = self.client.post(
            "/api/rag/plans/plan_1/approve",
            json={"plan_hash": "x"},
            headers={"X-SCIPAL-Internal-Token": "agent"},
        )
        self.assertEqual(response.status_code, 403)

    def test_approval_requires_human_session(self) -> None:
        response = self.client.post("/api/rag/plans/plan_1/approve", json={"plan_hash": "x"})
        self.assertEqual(response.status_code, 403)

    def test_worker_lease_requires_token(self) -> None:
        with mock.patch.dict("os.environ", {"SCIPAL_RAG_WORKER_TOKEN": "secret"}):
            response = self.client.post("/api/rag/jobs/lease", json={"worker_id": "w"})
        self.assertEqual(response.status_code, 403)

    def test_worker_lease_with_token(self) -> None:
        with mock.patch.dict("os.environ", {"SCIPAL_RAG_WORKER_TOKEN": "secret"}), \
             mock.patch("routes.rag_control.lease_job", return_value={"job_id": "job_1"}):
            response = self.client.post(
                "/api/rag/jobs/lease",
                json={"worker_id": "w"},
                headers={"X-SCIPAL-RAG-Worker-Token": "secret"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["job"]["job_id"], "job_1")


if __name__ == "__main__":
    unittest.main()
