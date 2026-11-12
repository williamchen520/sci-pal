"""Platform library registry route tests (store is mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.libraries import build_libraries_blueprint


def make_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "test"
    app.register_blueprint(build_libraries_blueprint())
    return app


class LibraryRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = make_app()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = "user_1"
            session["workspace_id"] = "ws_1"

    def test_create_code_library(self) -> None:
        library = {
            "library_id": "lib_abc",
            "workspace_id": "ws_1",
            "kind": "code",
            "name": "scanpy",
            "status": "registered",
        }
        with mock.patch("routes.libraries.resolve_workspace", return_value="ws_1"), \
             mock.patch("routes.libraries.authorize", return_value=True), \
             mock.patch("routes.libraries.create_library", return_value=library) as create:
            response = self.client.post(
                "/api/libraries",
                json={
                    "name": "scanpy",
                    "kind": "code",
                    "config": {"repo_url": "https://github.com/scverse/scanpy"},
                },
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["library_id"], "lib_abc")
        self.assertEqual(create.call_args.kwargs["kind"], "code")

    def test_code_library_requires_repo_url(self) -> None:
        with mock.patch("routes.libraries.resolve_workspace", return_value="ws_1"), \
             mock.patch("routes.libraries.authorize", return_value=True):
            response = self.client.post(
                "/api/libraries", json={"name": "x", "kind": "code", "config": {}}
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("repo_url", response.get_json()["error"])

    def test_list_is_workspace_scoped(self) -> None:
        with mock.patch("routes.libraries.resolve_workspace", return_value="ws_1"), \
             mock.patch("routes.libraries.authorize", return_value=True), \
             mock.patch("routes.libraries.list_libraries", return_value=[]) as listing:
            response = self.client.get("/api/libraries?kind=code")
        self.assertEqual(response.status_code, 200)
        listing.assert_called_once_with(workspace_id="ws_1", kind="code")

    def test_read_denied(self) -> None:
        with mock.patch("routes.libraries.resolve_workspace", return_value="ws_1"), \
             mock.patch("routes.libraries.authorize", return_value=False):
            response = self.client.get("/api/libraries")
        self.assertEqual(response.status_code, 403)

    def test_detail_rejects_other_workspace(self) -> None:
        with mock.patch("routes.libraries.resolve_workspace", return_value="ws_1"), \
             mock.patch("routes.libraries.authorize", return_value=True), \
             mock.patch("routes.libraries.get_library", return_value={"workspace_id": "ws_2"}):
            response = self.client.get("/api/libraries/lib_other")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
