"""Abstracts routes (PostgreSQL mocked)."""

from __future__ import annotations

import unittest
from unittest import mock

from flask import Flask

from routes.abstracts import build_abstracts_blueprint


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


ROWS = [
    {
        "pmid": "1",
        "doi": "10.1/a",
        "title": "Sepsis review",
        "abstract": "sepsis abstract",
        "authors": "A",
        "journal": "J",
        "year": 2026,
        "topic": "sepsis",
        "source": "abstract",
    },
    {
        "pmid": "2",
        "doi": "10.1/b",
        "title": "Liver cancer",
        "abstract": "liver abstract",
        "authors": "B",
        "journal": "J",
        "year": 2025,
        "topic": "hcc",
        "source": "abstract",
    },
]


class FakePG:
    def execute(self, sql, params):
        if "COUNT" in sql:
            total = 1 if any("sepsis" in str(p) for p in params) else 2
            return Cursor(row={"total": total})
        if "FROM abstracts" in sql and "pmid=%s" in sql:
            pmid = params[0]
            return Cursor(row=next((row for row in ROWS if row["pmid"] == pmid), None))
        rows = [row for row in ROWS if any("sepsis" in str(p) for p in params)] if len(params) >= 4 else ROWS
        return Cursor(rows=rows)

    def close(self):
        pass


def make_app():
    app = Flask(__name__)
    app.register_blueprint(build_abstracts_blueprint())
    return app


class AbstractRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patch = mock.patch("routes.abstracts._pg", return_value=FakePG())
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = make_app().test_client()

    def test_list_returns_papers(self) -> None:
        body = self.client.get("/api/abstracts/list").get_json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["papers"]), 2)

    def test_search_filters(self) -> None:
        body = self.client.get("/api/abstracts/list?search=sepsis").get_json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["papers"][0]["paper_id"], "1")

    def test_detail_returns_abstract(self) -> None:
        body = self.client.get("/api/abstracts/1").get_json()
        self.assertEqual(body["title"], "Sepsis review")
        self.assertIn("sepsis abstract", body["abstract"])

    def test_missing_abstract_returns_404(self) -> None:
        self.assertEqual(self.client.get("/api/abstracts/999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
