"""R11 agreement/kappa tests."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.rag_control import build_rag_control_blueprint
from services.rag_control.agreement import cohen_kappa


class KappaTests(unittest.TestCase):
    def test_perfect_agreement(self) -> None:
        labels = ["accept", "accept", "reject", "reject"]
        self.assertEqual(cohen_kappa(labels, labels), 1.0)

    def test_known_disagreement(self) -> None:
        a = ["accept", "accept", "reject", "reject"]
        b = ["accept", "reject", "accept", "reject"]
        self.assertLess(cohen_kappa(a, b), 0.1)

    def test_single_rater_is_not_available(self) -> None:
        app = Flask(__name__)
        app.register_blueprint(build_rag_control_blueprint())
        client = app.test_client()
        with mock.patch(
            "routes.rag_control.agreement",
            return_value={"reviewer_count": 1, "pairwise": [], "sufficient": False},
        ):
            response = client.get("/api/rag/multi/m/agreement")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["sufficient"])


if __name__ == "__main__":
    unittest.main()
