"""R12 reviewer assignment tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint


class AssignmentRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_list_assignments(self) -> None:
        with mock.patch("routes.rag_control.list_assignments", return_value=[{"assignment_id": "a"}]):
            response = self.client.get("/api/rag/multi/m/assignments")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["assignments"][0]["assignment_id"], "a")

    def test_assignment_requires_human(self) -> None:
        response = self.client.post(
            "/api/rag/multi/m/assignments",
            json={"rag_id": "code", "reviewer_user_id": "u"},
        )
        self.assertEqual(response.status_code, 403)

    def test_assignment_owner(self) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = "owner"
        with mock.patch("routes.rag_control.get_multi", return_value={"workspace_id": "ws"}), \
             mock.patch("routes.rag_control.authorize", return_value=True), \
             mock.patch("routes.rag_control.assign", return_value={"assignment_id": "a"}):
            response = self.client.post(
                "/api/rag/multi/m/assignments",
                json={"rag_id": "code", "reviewer_user_id": "u"},
            )
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
