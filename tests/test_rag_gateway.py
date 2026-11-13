"""R5 gateway route tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint
from services.rag_control.gateway import GatewayError, query


class RagGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_query_route(self) -> None:
        with mock.patch("routes.rag_control.gateway_query", return_value={"run_id": "q", "results": []}):
            response = self.client.post(
                "/api/rag/query",
                json={"capability": "code_search", "library_id": "lib", "query": "x"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["run_id"], "q")

    def test_query_rejects_unknown_capability(self) -> None:
        response = self.client.post(
            "/api/rag/query",
            json={"capability": "paper_search", "library_id": "lib", "query": "x"},
        )
        self.assertEqual(response.status_code, 400)

    def test_gateway_rejects_unknown_capability(self) -> None:
        with self.assertRaises(GatewayError):
            query(capability="paper_search", library_id="lib", query_text="x")


if __name__ == "__main__":
    unittest.main()
