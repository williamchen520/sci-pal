"""Tests for the durable review query routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.reviews import build_reviews_blueprint
from services.review.review_repository import ReviewRepository


def make_app(db_path: Path) -> Flask:
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(build_reviews_blueprint(db_path=db_path, log=app.logger))
    return app


class ReviewRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "research.db"
        self.repo = ReviewRepository(self.db)

    def test_empty_list(self) -> None:
        resp = make_app(self.db).test_client().get("/api/reviews")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["count"], 0)

    def test_list_omits_markdown_and_sorts_newest_first(self) -> None:
        self.repo.save(review_id="rev_old", topic="a", markdown="old", created_at="2026-01-01T00:00:00Z")
        self.repo.save(review_id="rev_new", topic="b", markdown="new", created_at="2026-02-01T00:00:00Z")

        resp = make_app(self.db).test_client().get("/api/reviews?limit=10")
        reviews = resp.get_json()["data"]["reviews"]
        self.assertEqual([item["review_id"] for item in reviews], ["rev_new", "rev_old"])
        self.assertNotIn("markdown", reviews[0])

    def test_get_review_returns_markdown(self) -> None:
        self.repo.save(review_id="rev_1", topic="demo", markdown="# body", stats={"verified": 1})
        resp = make_app(self.db).test_client().get("/api/reviews/rev_1")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["markdown"], "# body")
        self.assertEqual(data["stats"], {"verified": 1})

    def test_get_missing_review(self) -> None:
        resp = make_app(self.db).test_client().get("/api/reviews/rev_nope")
        self.assertEqual(resp.status_code, 404)
        body = resp.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["kind"], "not_found")

    def test_bad_limit_falls_back(self) -> None:
        resp = make_app(self.db).test_client().get("/api/reviews?limit=abc")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
