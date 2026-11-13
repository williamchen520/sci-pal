"""R4 evidence/artifact route tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint


class RagLedgerRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_evidence_list(self) -> None:
        with mock.patch("routes.rag_control.list_evidence", return_value=[{"evidence_id": "e"}]):
            response = self.client.get("/api/rag/runs/run_1/evidence")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["evidence"][0]["evidence_id"], "e")

    def test_evidence_requires_worker(self) -> None:
        with mock.patch.dict("os.environ", {"SCIPAL_RAG_WORKER_TOKEN": "secret"}):
            response = self.client.post("/api/rag/runs/run_1/evidence", json={})
        self.assertEqual(response.status_code, 403)

    def test_artifact_append(self) -> None:
        with mock.patch.dict("os.environ", {"SCIPAL_RAG_WORKER_TOKEN": "secret"}), \
             mock.patch("routes.rag_control.append_artifact", return_value={"artifact_id": "a"}):
            response = self.client.post(
                "/api/rag/runs/run_1/artifacts",
                json={"kind": "run_manifest", "uri": "/tmp/x"},
                headers={"X-SCIPAL-RAG-Worker-Token": "secret"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["artifact_id"], "a")


if __name__ == "__main__":
    unittest.main()
