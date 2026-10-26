"""Abstracts routes (moved out of api_server)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.abstracts import build_abstracts_blueprint


def make_app(db_path: Path):
    app = Flask(__name__)
    app.register_blueprint(build_abstracts_blueprint(db_path=db_path))
    return app


class AbstractRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "abstracts.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE papers (pmid TEXT, doi TEXT, title TEXT, abstract TEXT, "
            "authors TEXT, journal TEXT, year INTEGER, topic TEXT)"
        )
        conn.execute(
            "INSERT INTO papers VALUES ('1', '10.1/a', 'Sepsis review', 'sepsis abstract', "
            "'A', 'J', 2026, 'sepsis')"
        )
        conn.execute(
            "INSERT INTO papers VALUES ('2', '10.1/b', 'Liver cancer', 'liver abstract', "
            "'B', 'J', 2025, 'hcc')"
        )
        conn.commit()
        conn.close()
        self.client = make_app(self.db).test_client()

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

    def test_missing_db_returns_404(self) -> None:
        client = make_app(Path(self.tmp.name) / "nope.db").test_client()
        self.assertEqual(client.get("/api/abstracts/list").status_code, 404)


if __name__ == "__main__":
    unittest.main()
