"""R13 finalization gate tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint
from services.rag_control import finalization


class FinalizationGateTests(unittest.TestCase):
    def test_single_reviewer_cannot_finalize(self) -> None:
        run = {"multi_run_id": "m", "status": "open"}
        with mock.patch("services.rag_control.finalization.get_multi", return_value=run), \
             mock.patch(
                 "services.rag_control.finalization.agreement",
                 return_value={"reviewer_count": 1},
             ):
            with self.assertRaises(finalization.FinalizationError):
                finalization.finalize(
                    multi_run_id="m", decision="accepted", note="", finalized_by="u"
                )


class FinalizationRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_finalize_requires_human(self) -> None:
        response = self.client.post(
            "/api/rag/multi/m/finalize",
            json={"decision": "accepted"},
        )
        self.assertEqual(response.status_code, 403)

    def test_finalize_requires_permission(self) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = "u"
        with mock.patch("routes.rag_control.get_multi", return_value={"workspace_id": "ws"}), \
             mock.patch("routes.rag_control.authorize", return_value=False):
            response = self.client.post(
                "/api/rag/multi/m/finalize",
                json={"decision": "accepted"},
            )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
