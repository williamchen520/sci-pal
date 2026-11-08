"""P7 ingest tracking route tests (store is mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from plugins.ingest_tracking.routes import build_ingest_tracking_blueprint


def make_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(build_ingest_tracking_blueprint())
    return app


class IngestTrackingRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = make_app()

    def test_create_batch(self) -> None:
        with mock.patch("plugins.ingest_tracking.routes.store.create_batch") as create:
            resp = self.app.test_client().post(
                "/api/ingest-tracking/batches",
                json={"batch_id": "b1", "source": "client", "total": 2},
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["batch_id"], "b1")
        create.assert_called_once()

    def test_add_item_and_finding(self) -> None:
        with mock.patch(
            "plugins.ingest_tracking.routes.store.add_item", return_value=7
        ) as add_item, mock.patch(
            "plugins.ingest_tracking.routes.store.add_finding"
        ) as add_finding:
            resp = self.app.test_client().post(
                "/api/ingest-tracking/batches/b1/items",
                json={
                    "filename": "x.xml",
                    "paper_id": "p1",
                    "quality_status": "needs_review",
                    "flags": [{"code": "DQ001", "severity": "warn", "message": "m"}],
                },
            )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.get_json()["item_id"], 7)
        add_finding.assert_called_once()

    def test_invalid_status(self) -> None:
        resp = self.app.test_client().post(
            "/api/ingest-tracking/batches/b1/items",
            json={"filename": "x.xml", "quality_status": "oops"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_get_batch_missing(self) -> None:
        with mock.patch("plugins.ingest_tracking.routes.store.get_batch", return_value=None):
            resp = self.app.test_client().get("/api/ingest-tracking/batches/nope")
        self.assertEqual(resp.status_code, 404)

    def test_review_paper(self) -> None:
        with mock.patch(
            "plugins.ingest_tracking.routes.store.review_paper", return_value=True
        ):
            resp = self.app.test_client().post(
                "/api/ingest-tracking/papers/p1/review",
                json={"quality_status": "reviewed"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["quality_status"], "reviewed")


if __name__ == "__main__":
    unittest.main()
