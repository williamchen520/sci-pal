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

    def test_conflict_requires_human(self) -> None:
        response = self.client.post(
            "/api/rag/multi/m/conflicts",
            json={"rag_id": "code", "note": "x"},
        )
        self.assertEqual(response.status_code, 403)

    def test_export(self) -> None:
        with mock.patch("routes.rag_control.get_multi", return_value={"multi_run_id": "m"}):
            response = self.client.get("/api/rag/multi/m/export.json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))

    def test_reviewer_permission_required(self) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = "u"
        with mock.patch("routes.rag_control.get_multi", return_value={"workspace_id": "ws"}), \
             mock.patch("routes.rag_control.authorize", return_value=False):
            response = self.client.post(
                "/api/rag/multi/m/adjudications",
                json={"rag_id": "code", "decision": "accept"},
            )
        self.assertEqual(response.status_code, 403)

    def test_reviewer_can_adjudicate(self) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = "u"
        with mock.patch("routes.rag_control.get_multi", return_value={"workspace_id": "ws"}), \
             mock.patch("routes.rag_control.authorize", return_value=True), \
             mock.patch("routes.rag_control.add_adjudication", return_value={"adjudication_id": "a"}):
            response = self.client.post(
                "/api/rag/multi/m/adjudications",
                json={"rag_id": "code", "decision": "accept"},
            )
        self.assertEqual(response.status_code, 201)

    def test_adjudication_requires_human(self) -> None:
        response = self.client.post(
            "/api/rag/multi/m/adjudications",
            json={"rag_id": "code", "decision": "accept"},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
