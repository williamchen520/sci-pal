"""PI read/copy semantics for projects."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.projects import build_projects_blueprint
from services.tenancy import add_member, create_user, create_workspace


class PICopyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "pi.db"
        self.owner = create_user("owner", "long-enough-password", db_path=self.db)
        self.pi = create_user("pi_user", "long-enough-password", db_path=self.db)
        self.member = create_user("member", "long-enough-password", db_path=self.db)
        self.ws = create_workspace("Lab", self.owner["user_id"], db_path=self.db)["workspace_id"]
        add_member(self.ws, self.pi["user_id"], "pi", db_path=self.db)
        add_member(self.ws, self.member["user_id"], "member", db_path=self.db)
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_projects_blueprint(db_path=self.db))
        self.client = app.test_client()

    def login(self, user: dict) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = self.ws

    def create_member_project(self, data_class: str = "internal") -> str:
        self.login(self.member)
        project_id = self.client.post("/api/projects", json={"name": "Member project"}).get_json()["project_id"]
        conn = sqlite3.connect(self.db)
        conn.execute("UPDATE projects SET data_class = ? WHERE project_id = ?", (data_class, project_id))
        conn.commit()
        conn.close()
        return project_id

    def test_pi_can_read_and_copy_internal_project(self) -> None:
        project_id = self.create_member_project()
        self.login(self.pi)
        self.assertEqual(self.client.get(f"/api/projects/{project_id}").status_code, 200)
        copied = self.client.post(f"/api/projects/{project_id}/copy")
        self.assertEqual(copied.status_code, 201)
        copy = copied.get_json()
        self.assertEqual(copy["owner_user_id"], self.pi["user_id"])
        self.assertEqual(copy["copied_from"], project_id)
        conn = sqlite3.connect(self.db)
        actions = [row[0] for row in conn.execute("SELECT action FROM tenancy_audit")]
        conn.close()
        self.assertIn("pi.read", actions)
        self.assertIn("pi.copy", actions)

    def test_pi_cannot_copy_private_project(self) -> None:
        project_id = self.create_member_project(data_class="private")
        self.login(self.pi)
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/copy").status_code, 404)

    def test_member_cannot_copy_other_project(self) -> None:
        project_id = self.create_member_project()
        other = create_user("other", "long-enough-password", db_path=self.db)
        add_member(self.ws, other["user_id"], "member", db_path=self.db)
        self.login(other)
        self.assertEqual(self.client.post(f"/api/projects/{project_id}/copy").status_code, 404)


if __name__ == "__main__":
    unittest.main()
