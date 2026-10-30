"""Tenancy API routes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.tenancy import build_tenancy_blueprint
from services.tenancy import create_user


class TenancyRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "research.db"
        self.owner = create_user("owner", "long-enough-password", db_path=self.db)
        self.member = create_user("member", "long-enough-password", db_path=self.db)
        app = Flask(__name__)
        app.secret_key = "test-secret"
        app.register_blueprint(build_tenancy_blueprint(db_path=self.db))
        self.client = app.test_client()

    def login(self, username: str = "owner", password: str = "long-enough-password"):
        return self.client.post("/api/auth/login", json={"username": username, "password": password})

    def test_login_rejects_bad_password(self) -> None:
        response = self.login(password="wrong-password")
        self.assertEqual(response.status_code, 401)

    def test_login_and_me(self) -> None:
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["username"], "owner")
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.get_json()["user_id"], self.owner["user_id"])

    def test_unauthenticated_me(self) -> None:
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_create_workspace_and_list(self) -> None:
        self.login()
        created = self.client.post("/api/workspaces", json={"name": "Lab A"})
        self.assertEqual(created.status_code, 201)
        workspace_id = created.get_json()["workspace_id"]
        listed = self.client.get("/api/workspaces").get_json()["workspaces"]
        self.assertIn(workspace_id, {item["workspace_id"] for item in listed})

    def test_owner_can_add_member(self) -> None:
        self.login()
        workspace_id = self.client.post("/api/workspaces", json={"name": "Lab A"}).get_json()["workspace_id"]
        response = self.client.post(
            f"/api/workspaces/{workspace_id}/members",
            json={"username": "member", "role": "member"},
        )
        self.assertEqual(response.status_code, 201)
        members = self.client.get(f"/api/workspaces/{workspace_id}/members").get_json()["members"]
        self.assertEqual({item["username"] for item in members}, {"owner", "member"})

    def test_member_cannot_add_member(self) -> None:
        self.login("owner")
        workspace_id = self.client.post("/api/workspaces", json={"name": "Lab A"}).get_json()["workspace_id"]
        self.client.post(
            f"/api/workspaces/{workspace_id}/members",
            json={"username": "member", "role": "member"},
        )
        self.client.post("/api/auth/logout")
        self.login("member")
        response = self.client.post(
            f"/api/workspaces/{workspace_id}/members",
            json={"username": "owner", "role": "viewer"},
        )
        self.assertEqual(response.status_code, 403)

    def test_role_actions(self) -> None:
        self.login()
        workspace_id = self.client.post("/api/workspaces", json={"name": "Lab A"}).get_json()["workspace_id"]
        role = self.client.get(f"/api/workspaces/{workspace_id}/role").get_json()
        self.assertEqual(role["role"], "owner")
        self.assertIn("manage_members", role["actions"])

    def test_logout(self) -> None:
        self.login()
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)


if __name__ == "__main__":
    unittest.main()
