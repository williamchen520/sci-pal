"""Tests for the extracted papers blueprint (response shape must stay identical)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.papers import build_papers_blueprint


class FakeGraph:
    def __init__(self, neighbors=None, error=None, traversed=None):
        self._neighbors = neighbors or []
        self._error = error
        self._traversed = traversed or []
        self.calls = []

    def get_neighbors(self, ids, relation, direction):
        self.calls.append(("neighbors", ids, relation, direction))
        if self._error:
            raise self._error
        return list(self._neighbors)

    def traverse(self, ids, max_hops, max_total, relation):
        self.calls.append(("traverse", ids, max_hops, max_total, relation))
        if self._error:
            raise self._error
        return list(self._traversed)


def make_app(db_path: Path, graph) -> Flask:
    app = Flask(__name__)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.register_blueprint(
        build_papers_blueprint(db_path=db_path, get_graph=lambda: graph, log=app.logger)
    )
    return app


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT,
            year INTEGER, doi TEXT, total_paragraphs INTEGER,
            total_figures INTEGER, total_tables INTEGER
        );
        CREATE TABLE cross_paper_index (
            source_paper_id TEXT, target_paper_id TEXT, relation TEXT, confidence REAL
        );
        """
    )
    conn.execute(
        "INSERT INTO papers VALUES ('p1','Title One','A, B','J',2020,'10.1/p1',3,1,0)"
    )
    conn.execute(
        "INSERT INTO papers VALUES ('p2','Title Two','C, D','J',2021,'10.1/p2',2,0,0)"
    )
    conn.execute("INSERT INTO cross_paper_index VALUES ('p1','p2','cites',0.8)")
    conn.commit()
    conn.close()


class PaperListTests(unittest.TestCase):
    def test_list_shape_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            resp = make_app(db, FakeGraph()).test_client().get("/api/papers")
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["count"], 2)
        self.assertIn("paper_id", body["papers"][0])

    def test_detail_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            resp = make_app(db, FakeGraph()).test_client().get("/api/papers/nope")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json(), {"error": "Paper not found"})

    def test_detail_with_neighbors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            resp = make_app(db, FakeGraph()).test_client().get("/api/papers/p1")
        body = resp.get_json()
        self.assertEqual(body["paper"]["paper_id"], "p1")
        self.assertEqual([row["paper_id"] for row in body["cites"]], ["p2"])


class PaperGraphTests(unittest.TestCase):
    def test_one_hop_uses_get_neighbors(self) -> None:
        graph = FakeGraph(neighbors=[{"paper_id": "p2"}])
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            resp = make_app(db, graph).test_client().get("/api/papers/p1/graph")
        body = resp.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["max_hops"], 1)
        self.assertEqual(graph.calls[0][0], "neighbors")

    def test_two_hops_uses_traverse(self) -> None:
        graph = FakeGraph(traversed=[{"paper_id": "p2"}, {"paper_id": "p3"}])
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            resp = make_app(db, graph).test_client().get("/api/papers/p1/graph?max_hops=2")
        self.assertEqual(resp.get_json()["count"], 2)
        self.assertEqual(graph.calls[0][0], "traverse")

    def test_failure_keeps_legacy_error_shape(self) -> None:
        graph = FakeGraph(error=RuntimeError("boom"))
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            make_db(db)
            resp = make_app(db, graph).test_client().get("/api/papers/p1/graph")
        self.assertEqual(resp.status_code, 500)
        self.assertIn("Graph traversal failed", resp.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
