"""R2 model registry/route tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint


class RagModelRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_models(self) -> None:
        with mock.patch("routes.rag_control.list_models", return_value=[{"model_id": "m"}]):
            response = self.client.get("/api/rag/models")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["models"][0]["model_id"], "m")

    def test_binding_register_requires_worker(self) -> None:
        with mock.patch.dict("os.environ", {"SCIPAL_RAG_WORKER_TOKEN": "secret"}):
            response = self.client.post("/api/rag/index-bindings", json={"rag_id": "code"})
        self.assertEqual(response.status_code, 403)

    def test_binding_register(self) -> None:
        payload = {"rag_id": "code", "library_id": "lib", "index_name": "i", "embedding_model": "m"}
        with mock.patch.dict("os.environ", {"SCIPAL_RAG_WORKER_TOKEN": "secret"}), \
             mock.patch("routes.rag_control.register_binding", return_value={"binding_id": "b"}):
            response = self.client.post(
                "/api/rag/index-bindings",
                json=payload,
                headers={"X-SCIPAL-RAG-Worker-Token": "secret"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["binding_id"], "b")


if __name__ == "__main__":
    unittest.main()
