"""Project API workspace isolation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.projects import build_projects_blueprint
from services.tenancy import add_member, create_user, create_workspace


class ProjectRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "projects.db"
        self.alice = create_user("alice", "long-enough-password", db_path=self.db)
        self.bob = create_user("bob", "long-enough-password", db_path=self.db)
        self.ws_a = create_workspace("A", self.alice["user_id"], db_path=self.db)["workspace_id"]
        self.ws_b = create_workspace("B", self.bob["user_id"], db_path=self.db)["workspace_id"]
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_projects_blueprint(db_path=self.db))
        self.client = app.test_client()

    def login(self, user: dict, workspace_id: str) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = workspace_id

    def test_create_and_get(self) -> None:
        self.login(self.alice, self.ws_a)
        created = self.client.post("/api/projects", json={"name": "Project A"})
        self.assertEqual(created.status_code, 201)
        project_id = created.get_json()["project_id"]
        detail = self.client.get(f"/api/projects/{project_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["name"], "Project A")

    def test_other_workspace_cannot_read(self) -> None:
        self.login(self.alice, self.ws_a)
        project_id = self.client.post("/api/projects", json={"name": "A"}).get_json()["project_id"]
        self.login(self.bob, self.ws_b)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/projects").get_json()["projects"], [])

    def test_member_sees_joined_project(self) -> None:
        self.login(self.alice, self.ws_a)
        project_id = self.client.post("/api/projects", json={"name": "A"}).get_json()["project_id"]
        add_member(self.ws_a, self.bob["user_id"], "member", db_path=self.db)
        self.client.post(
            f"/api/projects/{project_id}/members",
            json={"user_id": self.bob["user_id"], "role": "member"},
        )
        self.login(self.bob, self.ws_a)
        self.assertEqual(len(self.client.get("/api/projects").get_json()["projects"]), 1)

    def test_non_owner_cannot_update(self) -> None:
        self.login(self.alice, self.ws_a)
        project_id = self.client.post("/api/projects", json={"name": "A"}).get_json()["project_id"]
        add_member(self.ws_a, self.bob["user_id"], "member", db_path=self.db)
        self.login(self.bob, self.ws_a)
        self.assertEqual(
            self.client.put(f"/api/projects/{project_id}", json={"name": "Hacked"}).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
