"""R18 seal key directory tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint


class SealKeyRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_list_keys(self) -> None:
        with mock.patch("routes.rag_control.list_keys", return_value=[{"key_id": "k"}]):
            response = self.client.get("/api/rag/seal-keys")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["keys"][0]["key_id"], "k")


if __name__ == "__main__":
    unittest.main()
