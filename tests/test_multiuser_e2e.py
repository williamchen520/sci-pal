"""End-to-end multi-user isolation across projects, papers and experiments."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.experiments import build_experiments_blueprint
from routes.notes import build_notes_blueprint
from routes.papers import build_papers_blueprint
from routes.projects import build_projects_blueprint
from routes.runs import build_runs_blueprint
from routes.tenancy import build_tenancy_blueprint
from services.tenancy import add_member, create_user, create_workspace


class MultiUserEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "e2e.db"
        self._create_schema()
        self.alice = create_user("alice", "long-enough-password", db_path=self.db)
        self.bob = create_user("bob", "long-enough-password", db_path=self.db)
        self.ws_a = create_workspace("Lab A", self.alice["user_id"], db_path=self.db)["workspace_id"]
        self.ws_b = create_workspace("Lab B", self.bob["user_id"], db_path=self.db)["workspace_id"]
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO papers VALUES ('p_a','A','authors','J',2026,'',?,0,0,0)", (self.ws_a,))
        conn.execute("INSERT INTO papers VALUES ('p_b','B','authors','J',2026,'',?,0,0,0)", (self.ws_b,))
        conn.commit()
        conn.close()
        app = Flask(__name__)
        app.secret_key = "e2e"
        app.register_blueprint(build_tenancy_blueprint(db_path=self.db))
        app.register_blueprint(build_papers_blueprint(db_path=self.db, get_graph=lambda: None, log=app.logger))
        app.register_blueprint(build_notes_blueprint(db_path=self.db))
        app.register_blueprint(build_projects_blueprint(db_path=self.db))
        app.register_blueprint(build_experiments_blueprint(db_path=self.db))
        app.register_blueprint(build_runs_blueprint(db_path=self.db))
        self.client = app.test_client()

    def _create_schema(self) -> None:
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT, journal TEXT,
                year INTEGER, doi TEXT, workspace_id TEXT,
                total_paragraphs INTEGER DEFAULT 0,
                total_figures INTEGER DEFAULT 0,
                total_tables INTEGER DEFAULT 0
            );
            CREATE TABLE protocol_imports (protocol_id TEXT PRIMARY KEY, title TEXT);
            INSERT INTO protocol_imports VALUES ('proto_1', 'Protocol');
            """
        )
        conn.commit()
        conn.close()

    def login(self, username: str) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "long-enough-password"},
        )
        self.assertEqual(response.status_code, 200)

    def test_cross_workspace_isolation(self) -> None:
        self.login("alice")
        project = self.client.post("/api/projects", json={"name": "Alice project"}).get_json()
        experiment = self.client.post(
            f"/api/projects/{project['project_id']}/experiments",
            json={"title": "Alice experiment", "protocol_id": "proto_1", "protocol_version": "1"},
        ).get_json()
        run = self.client.post(
            f"/api/experiments/{experiment['experiment_id']}/runs",
            json={"title": "Run", "planned": {"dose": 10}, "actual": {"dose": 8}},
        ).get_json()
        self.client.post("/api/notes", json={"content": "alice note", "paper_id": "p_a"})
        self.assertEqual(
            [item["paper_id"] for item in self.client.get("/api/papers").get_json()["papers"]],
            ["p_a"],
        )

        self.login("bob")
        self.assertEqual(self.client.get(f"/api/projects/{project['project_id']}").status_code, 404)
        self.assertEqual(
            [item["paper_id"] for item in self.client.get("/api/papers").get_json()["papers"]],
            ["p_b"],
        )
        self.assertEqual(self.client.get("/api/notes").get_json()["notes"], [])
        self.assertEqual(
            self.client.get(f"/api/experiments/{experiment['experiment_id']}").status_code,
            404,
        )
        self.assertEqual(self.client.get(f"/api/runs/{run['run_id']}").status_code, 404)

    def test_workspace_switch_changes_visible_data(self) -> None:
        self.login("alice")
        alice_paper_ids = {
            item["paper_id"] for item in self.client.get("/api/papers").get_json()["papers"]
        }
        self.assertEqual(alice_paper_ids, {"p_a"})
        self.client.post("/api/auth/workspace", json={"workspace_id": self.ws_b})
        # Alice is not a member of B; switching must be rejected.
        self.assertEqual(
            self.client.post("/api/auth/workspace", json={"workspace_id": self.ws_b}).status_code,
            403,
        )

    def test_project_member_cannot_read_owner_private_experiment(self) -> None:
        self.login("alice")
        project = self.client.post("/api/projects", json={"name": "P"}).get_json()
        experiment = self.client.post(
            f"/api/projects/{project['project_id']}/experiments",
            json={"title": "E", "protocol_id": "proto_1", "protocol_version": "1"},
        ).get_json()
        add_member(self.ws_a, self.bob["user_id"], "member", db_path=self.db)
        self.client.post(
            f"/api/projects/{project['project_id']}/members",
            json={"user_id": self.bob["user_id"], "role": "member"},
        )
        self.login("bob")
        self.assertEqual(self.client.get(f"/api/projects/{project['project_id']}").status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/experiments/{experiment['experiment_id']}").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
