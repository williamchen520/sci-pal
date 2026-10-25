"""Tests for the extracted system blueprint (no api_server import)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.system import build_system_blueprint


class FakeGraph:
    def __init__(self, stats=None, error=None):
        self._stats = stats or {}
        self._error = error

    def stats(self):
        if self._error:
            raise self._error
        return self._stats


def make_app(db_path: Path, graph) -> Flask:
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(build_system_blueprint(db_path=db_path, get_graph=lambda: graph, log=app.logger))
    return app


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT, year INTEGER);
        CREATE TABLE paper_communities (
            community_id INTEGER PRIMARY KEY, size INTEGER, representative_paper_id TEXT,
            summary TEXT, keywords TEXT, avg_year INTEGER
        );
        CREATE TABLE community_members (community_id INTEGER, paper_id TEXT, centrality REAL);
        """
    )
    conn.execute("INSERT INTO papers VALUES ('p1', 'Title One', 'A, B', 'J', 2020)")
    conn.execute("INSERT INTO papers VALUES ('p2', 'Title Two', 'C, D', 'J', 2021)")
    conn.execute("INSERT INTO paper_communities VALUES (1, 2, 'p1', 'sum', 'kw', 2020)")
    conn.execute("INSERT INTO community_members VALUES (1, 'p1', 0.9)")
    conn.execute("INSERT INTO community_members VALUES (1, 'p2', 0.5)")
    conn.commit()
    conn.close()


class GraphStatsTests(unittest.TestCase):
    def test_success_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp) / "x.db", FakeGraph({"nodes": 2, "edges": 1}))
            resp = app.test_client().get("/api/graph/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"], {"nodes": 2, "edges": 1})
        self.assertIsNone(body["error"])

    def test_failure_is_internal_and_hides_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = make_app(Path(tmp) / "x.db", FakeGraph(error=RuntimeError("secret path")))
            resp = app.test_client().get("/api/graph/stats")
        self.assertEqual(resp.status_code, 500)
        body = resp.get_json()
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["kind"], "internal")
        self.assertEqual(body["error"]["message"], "Graph stats failed")
        self.assertNotIn("secret", str(body))


class CommunitiesTests(unittest.TestCase):
    def test_missing_table_returns_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "empty.db"
            sqlite3.connect(db).close()
            app = make_app(db, FakeGraph())
            resp = app.test_client().get("/api/communities")
        self.assertEqual(resp.status_code, 404)
        body = resp.get_json()
        self.assertEqual(body["error"]["kind"], "not_found")
        self.assertIn("build_communities", body["error"]["message"])

    def test_lists_communities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            app = make_app(db, FakeGraph())
            resp = app.test_client().get("/api/communities")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["total_communities"], 1)
        self.assertEqual(data["total_papers"], 2)
        self.assertEqual(data["communities"][0]["representative"]["paper_id"], "p1")
        self.assertNotIn("members", data["communities"][0])

    def test_detailed_includes_members(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            app = make_app(db, FakeGraph())
            resp = app.test_client().get("/api/communities?detailed=1")
        members = resp.get_json()["data"]["communities"][0]["members"]
        self.assertEqual([m["paper_id"] for m in members], ["p1", "p2"])

    def test_min_size_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            app = make_app(db, FakeGraph())
            resp = app.test_client().get("/api/communities?min_size=5")
        data = resp.get_json()["data"]
        self.assertEqual(data["total_communities"], 0)

    def test_bad_min_size_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            app = make_app(db, FakeGraph())
            resp = app.test_client().get("/api/communities?min_size=abc")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
