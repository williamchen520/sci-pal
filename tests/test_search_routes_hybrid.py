"""Hybrid/online search routes moved out of api_server (blueprint)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from flask import Flask

from routes.search import build_search_blueprint


class FakeRetriever:
    def search_papers(self, **kwargs):
        return {"query": kwargs["query"], "total": 1, "papers": [{"title": "T"}]}


class FakeSearcher:
    def search(self, query, **kwargs):
        class Hit:
            source = "online_pubmed"

            def to_dict(self):
                return {"title": "online hit"}

        return [Hit()]


def make_app(retriever=None, fail: bool = False):
    app = Flask(__name__)

    def get_retriever():
        if fail:
            raise RuntimeError("retriever boom")
        return retriever or FakeRetriever()

    app.register_blueprint(
        build_search_blueprint(
            get_task_manager=lambda: None,
            log=app.logger,
            get_hybrid_retriever=get_retriever,
        )
    )
    return app


class HybridRouteTests(unittest.TestCase):
    def test_post_returns_retriever_result(self) -> None:
        client = make_app().test_client()
        response = client.post("/api/search/hybrid", json={"q": "sepsis", "use_online": False})
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["query"], "sepsis")
        self.assertEqual(body["total"], 1)

    def test_get_works_too(self) -> None:
        client = make_app().test_client()
        self.assertEqual(client.get("/api/search/hybrid?q=x").status_code, 200)

    def test_missing_query_returns_400(self) -> None:
        client = make_app().test_client()
        self.assertEqual(client.post("/api/search/hybrid", json={}).status_code, 400)

    def test_retriever_error_returns_500(self) -> None:
        client = make_app(fail=True).test_client()
        self.assertEqual(client.post("/api/search/hybrid", json={"q": "x"}).status_code, 500)


class OnlineRouteTests(unittest.TestCase):
    def test_online_search_counts_sources(self) -> None:
        client = make_app().test_client()
        with patch("services.search.online_search.get_online_searcher", return_value=FakeSearcher()):
            response = client.post("/api/search/online", json={"q": "x", "max_results": 1})
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["pubmed_count"], 1)
        self.assertEqual(body["total"], 1)


if __name__ == "__main__":
    unittest.main()
