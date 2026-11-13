"""R7 multi evidence/adjudication route tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint


class AdjudicationRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_multi_list(self) -> None:
        with mock.patch("routes.rag_control.list_multi", return_value=[{"multi_run_id": "m"}]):
            response = self.client.get("/api/rag/multi")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["multi_runs"][0]["multi_run_id"], "m")

    def test_adjudication_rejects_agent(self) -> None:
        response = self.client.post(
            "/api/rag/multi/m/adjudications",
            json={"rag_id": "code", "decision": "accept"},
            headers={"X-SCIPAL-Internal-Token": "agent"},
        )
        self.assertEqual(response.status_code, 403)

    def test_adjudication_requires_human(self) -> None:
        response = self.client.post(
            "/api/rag/multi/m/adjudications",
            json={"rag_id": "code", "decision": "accept"},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
