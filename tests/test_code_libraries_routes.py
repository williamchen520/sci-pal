"""Proxy route tests for the code library UI."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from flask import Flask

from routes.code_libraries import build_code_libraries_blueprint


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"ok": True}).encode()


class CodeLibraryProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_code_libraries_blueprint())
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = "u1"
            session["workspace_id"] = "ws1"

    def _library(self, kind="code", workspace="ws1"):
        return {"library_id": "lib_1", "kind": kind, "workspace_id": workspace}

    def test_status_proxies(self) -> None:
        with mock.patch("routes.code_libraries.resolve_workspace", return_value="ws1"), \
             mock.patch("routes.code_libraries.authorize", return_value=True), \
             mock.patch("routes.code_libraries.get_library", return_value=self._library()), \
             mock.patch("routes.code_libraries.urllib.request.urlopen", return_value=_Response()):
            response = self.client.get("/api/code/libraries/lib_1/status")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_search_requires_query(self) -> None:
        with mock.patch("routes.code_libraries.resolve_workspace", return_value="ws1"), \
             mock.patch("routes.code_libraries.authorize", return_value=True), \
             mock.patch("routes.code_libraries.get_library", return_value=self._library()):
            response = self.client.post("/api/code/libraries/lib_1/search", json={})
        self.assertEqual(response.status_code, 400)

    def test_rejects_non_code_library(self) -> None:
        with mock.patch("routes.code_libraries.resolve_workspace", return_value="ws1"), \
             mock.patch("routes.code_libraries.authorize", return_value=True), \
             mock.patch("routes.code_libraries.get_library", return_value=self._library(kind="docs")):
            response = self.client.get("/api/code/libraries/lib_1/status")
        self.assertEqual(response.status_code, 400)

    def test_rejects_other_workspace(self) -> None:
        with mock.patch("routes.code_libraries.resolve_workspace", return_value="ws1"), \
             mock.patch("routes.code_libraries.authorize", return_value=True), \
             mock.patch("routes.code_libraries.get_library", return_value=self._library(workspace="ws2")):
            response = self.client.get("/api/code/libraries/lib_1/status")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
