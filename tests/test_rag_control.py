"""R0 RAG control plane tests."""

from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint
from services.rag_control.registry import _check_postgres, load_manifests, manifest_hash


class RagRegistryTests(unittest.TestCase):
    def test_manifests_are_hashable(self) -> None:
        manifests = load_manifests()
        self.assertEqual(len(manifests), 3)
        hashes = {manifest_hash(manifest) for manifest in manifests}
        self.assertEqual(len(hashes), 3)

    def test_missing_dsn_is_unknown_not_healthy(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            status, detail = _check_postgres({"dsn_env": "SCIPAL_DOCS_DSN"})
        self.assertEqual(status, "unknown")
        self.assertIn("SCIPAL_DOCS_DSN", detail)


class RagControlRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        self.client = app.test_client()

    def test_list(self) -> None:
        with mock.patch("routes.rag_control.list_providers", return_value=[{"rag_id": "code"}]):
            response = self.client.get("/api/rag/providers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["providers"][0]["rag_id"], "code")

    def test_missing_provider(self) -> None:
        with mock.patch("routes.rag_control.get_provider", return_value=None):
            response = self.client.get("/api/rag/providers/nope")
        self.assertEqual(response.status_code, 404)

    def test_health(self) -> None:
        with mock.patch("routes.rag_control.check_health", return_value={"rag_id": "code", "status": "active"}):
            response = self.client.get("/api/rag/providers/code/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "active")


if __name__ == "__main__":
    unittest.main()
