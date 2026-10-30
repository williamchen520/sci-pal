"""Experiment run records."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.experiments import build_experiments_blueprint
from routes.projects import build_projects_blueprint
from routes.runs import build_runs_blueprint
from services.tenancy import add_member, create_user, create_workspace


class RunRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "runs.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE protocol_imports (protocol_id TEXT PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO protocol_imports VALUES ('proto_1', 'Protocol')")
        conn.commit()
        conn.close()
        self.owner = create_user("owner", "long-enough-password", db_path=self.db)
        self.alice = create_user("alice", "long-enough-password", db_path=self.db)
        self.bob = create_user("bob", "long-enough-password", db_path=self.db)
        self.ws = create_workspace("Lab", self.owner["user_id"], db_path=self.db)["workspace_id"]
        add_member(self.ws, self.alice["user_id"], "member", db_path=self.db)
        add_member(self.ws, self.bob["user_id"], "member", db_path=self.db)
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_projects_blueprint(db_path=self.db))
        app.register_blueprint(build_experiments_blueprint(db_path=self.db))
        app.register_blueprint(build_runs_blueprint(db_path=self.db))
        self.client = app.test_client()
        self.login(self.owner)
        self.project_id = self.client.post("/api/projects", json={"name": "P"}).get_json()["project_id"]
        for user in (self.alice, self.bob):
            self.client.post(
                f"/api/projects/{self.project_id}/members",
                json={"user_id": user["user_id"], "role": "member"},
            )
        self.login(self.alice)
        self.experiment_id = self.client.post(
            f"/api/projects/{self.project_id}/experiments",
            json={"title": "E", "protocol_id": "proto_1", "protocol_version": "1"},
        ).get_json()["experiment_id"]

    def login(self, user: dict) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = self.ws

    def test_create_and_list_run(self) -> None:
        self.login(self.alice)
        created = self.client.post(
            f"/api/experiments/{self.experiment_id}/runs",
            json={
                "title": "Run 1",
                "planned": {"dose": 10},
                "actual": {"dose": 8},
                "observations": "ok",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.get_json()["planned_json"], '{"dose": 10}')
        rows = self.client.get(f"/api/experiments/{self.experiment_id}/runs").get_json()["runs"]
        self.assertEqual(len(rows), 1)

    def test_update_run(self) -> None:
        self.login(self.alice)
        run_id = self.client.post(
            f"/api/experiments/{self.experiment_id}/runs", json={"title": "Run"}
        ).get_json()["run_id"]
        updated = self.client.put(
            f"/api/runs/{run_id}", json={"status": "completed", "result": "ok"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["status"], "completed")

    def test_other_member_cannot_read_runs(self) -> None:
        self.login(self.alice)
        run_id = self.client.post(
            f"/api/experiments/{self.experiment_id}/runs", json={"title": "Run"}
        ).get_json()["run_id"]
        self.login(self.bob)
        self.assertEqual(self.client.get(f"/api/runs/{run_id}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/experiments/{self.experiment_id}/runs").status_code,
            404,
        )

    def test_run_requires_experiment_owner(self) -> None:
        self.login(self.bob)
        self.assertEqual(
            self.client.post(
                f"/api/experiments/{self.experiment_id}/runs", json={"title": "X"}
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
