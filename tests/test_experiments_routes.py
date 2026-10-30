"""Experiment records are owner-private within a project."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.experiments import build_experiments_blueprint
from routes.projects import build_projects_blueprint
from services.tenancy import add_member, create_user, create_workspace


class ExperimentRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "experiments.db"
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
        self.client = app.test_client()
        self.project_id = self._create_project()

    def _create_project(self) -> str:
        self.login(self.owner)
        project_id = self.client.post("/api/projects", json={"name": "Project"}).get_json()["project_id"]
        self.client.post(
            f"/api/projects/{project_id}/members",
            json={"user_id": self.alice["user_id"], "role": "member"},
        )
        self.client.post(
            f"/api/projects/{project_id}/members",
            json={"user_id": self.bob["user_id"], "role": "member"},
        )
        return project_id

    def login(self, user: dict) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = self.ws

    def test_create_and_list_own(self) -> None:
        self.login(self.alice)
        created = self.client.post(
            f"/api/projects/{self.project_id}/experiments",
            json={"title": "Run A", "status": "planned"},
        )
        self.assertEqual(created.status_code, 201)
        rows = self.client.get(f"/api/projects/{self.project_id}/experiments").get_json()["experiments"]
        self.assertEqual([row["title"] for row in rows], ["Run A"])

    def test_member_cannot_see_other_member_record(self) -> None:
        self.login(self.alice)
        experiment_id = self.client.post(
            f"/api/projects/{self.project_id}/experiments", json={"title": "A"}
        ).get_json()["experiment_id"]
        self.login(self.bob)
        self.assertEqual(self.client.get(f"/api/experiments/{experiment_id}").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/projects/{self.project_id}/experiments").get_json()["experiments"],
            [],
        )

    def test_non_member_cannot_create(self) -> None:
        outsider = create_user("outsider", "long-enough-password", db_path=self.db)
        add_member(self.ws, outsider["user_id"], "viewer", db_path=self.db)
        self.login(outsider)
        self.assertEqual(
            self.client.post(
                f"/api/projects/{self.project_id}/experiments", json={"title": "X"}
            ).status_code,
            404,
        )

    def test_owner_updates_own_record(self) -> None:
        self.login(self.alice)
        experiment_id = self.client.post(
            f"/api/projects/{self.project_id}/experiments", json={"title": "A"}
        ).get_json()["experiment_id"]
        updated = self.client.put(
            f"/api/experiments/{experiment_id}",
            json={"status": "completed", "content": "done"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["status"], "completed")


if __name__ == "__main__":
    unittest.main()
