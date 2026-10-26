"""Tests for the guard routes."""

from __future__ import annotations

import unittest

from flask import Flask

from routes.guard import build_guard_blueprint
from services.quality.guard import GuardReport, Issue
from services.quality.lexicon import Entry, Lexicon


class FakeGuard:
    def __init__(self) -> None:
        self.lexicon = Lexicon(
            entries=[
                Entry("Gene", "1956", "EGFR", ("ERBB",), 20, 5, "ncbi_gene"),
                Entry("Disease", "D009369", "tumor", (), 100, 40, "ncbi_mesh"),
            ]
        )
        self.lexicon._build_index()

    def check(self, text: str) -> GuardReport:
        report = GuardReport()
        report.counts["known_curated"] = 1
        report.issues.append(Issue(term="EGFR", status="known_curated", detail="1956"))
        return report


def make_app():
    app = Flask(__name__)
    app.register_blueprint(build_guard_blueprint(get_guard=FakeGuard, log=app.logger))
    return app


class GuardRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_app().test_client()

    def test_check_returns_summary(self) -> None:
        resp = self.client.post("/api/guard/check", json={"text": "EGFR is a receptor " * 3})
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["counts"]["known_curated"], 1)

    def test_short_text_rejected(self) -> None:
        self.assertEqual(self.client.post("/api/guard/check", json={"text": "hi"}).status_code, 400)

    def test_stats(self) -> None:
        body = self.client.get("/api/guard/stats").get_json()
        self.assertEqual(body["entries"], 2)
        self.assertIn("Gene", body["by_type"])

    def test_term_lookup(self) -> None:
        body = self.client.get("/api/guard/term/EGFR").get_json()
        self.assertEqual(body["entries"][0]["canonical"], "EGFR")
        self.assertEqual(body["entries"][0]["tier"], "curated")

    def test_term_includes_abbreviation(self) -> None:
        body = self.client.get("/api/guard/term/PBMC").get_json()
        self.assertIn("peripheral blood mononuclear cell", body["abbreviation"])


if __name__ == "__main__":
    unittest.main()
