"""Draft a protocol from a review (method sentences only)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.protocols import build_protocols_blueprint
from services.protocols.from_review import build_protocol_payload
from services.protocols.service import ProtocolService

REVIEW = {
    "review_id": "rev_demo",
    "topic": "TLR4 signaling in sepsis",
    "markdown": (
        "# TLR4 signaling\n\n"
        "Sepsis remains a major cause of death worldwide. "
        "Macrophages were stimulated with LPS at 100 ng/mL for 6 h. "
        "Cells were washed twice with PBS and lysed for Western blot. "
        "We used CRISPR knockout to validate TLR4. "
        "The pathway is conserved across species."
    ),
}


class BuildPayloadTests(unittest.TestCase):
    def test_only_method_sentences_become_steps(self) -> None:
        payload = build_protocol_payload(REVIEW)
        steps = payload["protocol"]["steps"]
        self.assertEqual(len(steps), 3)
        self.assertTrue(all("were" in step["step"] or "We used" in step["step"] for step in steps))
        self.assertIn("（实验方案草稿）", payload["protocol"]["title"])
        self.assertEqual(payload["protocol"]["id"], "review_rev_demo")

    def test_empty_review_yields_empty_steps(self) -> None:
        payload = build_protocol_payload({"review_id": "r", "topic": "t", "markdown": ""})
        self.assertEqual(payload["protocol"]["steps"], [])


class FakeReviewRepo:
    def __init__(self, review):
        self.review = review

    def get(self, review_id):
        return self.review if review_id == self.review["review_id"] else None


class ReviewToProtocolRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.service = ProtocolService(Path(self.tmp.name) / "p.db")

        class ServiceWrapper:
            def import_payload(inner, payload, url=""):
                return self.service.import_payload(payload, url=url)

            def get(inner, protocol_id):
                return self.service.get(protocol_id)

            def list(inner, limit=50, offset=0, query=""):
                return self.service.list(limit, offset, query)

            def count(inner, query=""):
                return self.service.count(query)

        app = Flask(__name__)
        app.register_blueprint(
            build_protocols_blueprint(
                get_service=lambda: ServiceWrapper(),
                log=app.logger,
                get_review_repo=lambda: FakeReviewRepo(REVIEW),
            )
        )
        self.client = app.test_client()

    def test_review_to_protocol_creates_draft(self) -> None:
        response = self.client.post("/api/reviews/rev_demo/to-protocol")
        body = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["protocol_id"], "review_rev_demo")
        self.assertEqual(body["steps"], 3)
        detail = self.client.get("/api/protocols/review_rev_demo").get_json()
        self.assertIn("实验方案草稿", detail["protocol"]["title"])

    def test_missing_review_returns_404(self) -> None:
        self.assertEqual(self.client.post("/api/reviews/nope/to-protocol").status_code, 404)

    def test_review_without_methods_returns_400(self) -> None:
        class EmptyRepo:
            def get(inner, review_id):
                return {"review_id": "rev_empty", "topic": "t", "markdown": "Just a claim."}

        app = Flask(__name__)
        app.register_blueprint(
            build_protocols_blueprint(
                get_service=lambda: self.service,
                log=app.logger,
                get_review_repo=EmptyRepo,
            )
        )
        response = app.test_client().post("/api/reviews/rev_empty/to-protocol")
        self.assertEqual(response.status_code, 400)
        self.assertIn("未找到方法类句子", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
