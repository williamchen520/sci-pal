"""P6 federated search route tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

from routes.search import build_search_blueprint


class FakeRetriever:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [{"identity": "doi:10.1/x", "paper_id": "p1", "score": 1.0, "libraries": ["main", "bench"]}]


def make_app(db: Path, retriever: FakeRetriever) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(
        build_search_blueprint(
            get_task_manager=lambda: None,
            log=app.logger,
            get_federated_retriever=lambda: retriever,
            db_path=str(db),
        )
    )
    return app


class FederatedRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "x.db"
        self.retriever = FakeRetriever()
        self.app = make_app(self.db, self.retriever)
        self.patch = mock.patch("routes.search.resolve_workspace", return_value="ws_default")
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_federated_get(self) -> None:
        resp = self.app.test_client().get(
            "/api/search/federated?q=cancer&library_scope=main,bench&quota_per_scope=1"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["results"][0]["identity"], "doi:10.1/x")
        self.assertEqual(self.retriever.calls[0][1]["scopes"], ["main", "bench"])
        self.assertEqual(self.retriever.calls[0][1]["quota_per_scope"], 1)

    def test_federated_post(self) -> None:
        resp = self.app.test_client().post(
            "/api/search/federated",
            json={"q": "cancer", "top_k": 5, "library_scope": "bench"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.retriever.calls[0][1]["scopes"], ["bench"])

    def test_missing_query(self) -> None:
        resp = self.app.test_client().get("/api/search/federated")
        self.assertEqual(resp.status_code, 400)

    def test_invalid_scope(self) -> None:
        resp = self.app.test_client().get("/api/search/federated?q=x&library_scope=all")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
