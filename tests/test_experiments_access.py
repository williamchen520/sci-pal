"""Protocol requirement and PI access requests for experiments."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.experiments import build_experiments_blueprint
from routes.projects import build_projects_blueprint
from services.tenancy import add_member, create_user, create_workspace


class ExperimentAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "elN.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE protocol_imports (protocol_id TEXT PRIMARY KEY, title TEXT)")
        conn.execute("INSERT INTO protocol_imports VALUES ('proto_1', 'Protocol')")
        conn.commit()
        conn.close()
        self.owner = create_user("owner", "long-enough-password", db_path=self.db)
        self.member = create_user("member", "long-enough-password", db_path=self.db)
        self.pi = create_user("pi_user", "long-enough-password", db_path=self.db)
        self.ws = create_workspace("Lab", self.owner["user_id"], db_path=self.db)["workspace_id"]
        add_member(self.ws, self.member["user_id"], "member", db_path=self.db)
        add_member(self.ws, self.pi["user_id"], "pi", db_path=self.db)
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_projects_blueprint(db_path=self.db))
        app.register_blueprint(build_experiments_blueprint(db_path=self.db))
        self.client = app.test_client()
        self.login(self.owner)
        self.project_id = self.client.post("/api/projects", json={"name": "P"}).get_json()["project_id"]
        for user in (self.member, self.pi):
            self.client.post(
                f"/api/projects/{self.project_id}/members",
                json={"user_id": user["user_id"], "role": "member"},
            )

    def login(self, user: dict) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = self.ws

    def create_experiment(self) -> str:
        self.login(self.member)
        return self.client.post(
            f"/api/projects/{self.project_id}/experiments",
            json={
                "title": "Run",
                "protocol_id": "proto_1",
                "protocol_version": "1",
            },
        ).get_json()["experiment_id"]

    def test_protocol_required(self) -> None:
        self.login(self.member)
        missing = self.client.post(
            f"/api/projects/{self.project_id}/experiments", json={"title": "No protocol"}
        )
        self.assertEqual(missing.status_code, 400)
        unknown = self.client.post(
            f"/api/projects/{self.project_id}/experiments",
            json={"title": "Unknown", "protocol_id": "missing", "protocol_version": "1"},
        )
        self.assertEqual(unknown.status_code, 404)

    def test_pi_request_approve_then_read(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.pi)
        self.assertEqual(self.client.get(f"/api/experiments/{experiment_id}").status_code, 404)
        requested = self.client.post(f"/api/experiments/{experiment_id}/access-requests")
        self.assertEqual(requested.status_code, 201)
        request_id = requested.get_json()["request_id"]
        self.login(self.member)
        requests = self.client.get(f"/api/experiments/{experiment_id}/access-requests").get_json()["requests"]
        self.assertEqual(len(requests), 1)
        decided = self.client.post(
            f"/api/experiments/{experiment_id}/access-requests/{request_id}/decide",
            json={"approve": True, "hours": 24},
        )
        self.assertEqual(decided.status_code, 200)
        self.login(self.pi)
        self.assertEqual(self.client.get(f"/api/experiments/{experiment_id}").status_code, 200)
        conn = sqlite3.connect(self.db)
        actions = [row[0] for row in conn.execute("SELECT action FROM tenancy_audit")]
        conn.close()
        self.assertIn("pi.request", actions)
        self.assertIn("pi.approve", actions)
        self.assertIn("pi.read", actions)

    def test_owner_can_deny(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.pi)
        request_id = self.client.post(
            f"/api/experiments/{experiment_id}/access-requests"
        ).get_json()["request_id"]
        self.login(self.member)
        self.client.post(
            f"/api/experiments/{experiment_id}/access-requests/{request_id}/decide",
            json={"approve": False},
        )
        self.login(self.pi)
        self.assertEqual(self.client.get(f"/api/experiments/{experiment_id}").status_code, 404)

    def test_update_creates_revision_and_audit(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.member)
        updated = self.client.put(
            f"/api/experiments/{experiment_id}",
            json={"status": "completed", "content": "finished"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["current_revision"], 2)
        revisions = self.client.get(f"/api/experiments/{experiment_id}/revisions").get_json()["revisions"]
        self.assertEqual([row["revision"] for row in revisions], [2, 1])
        self.assertIn("finished", revisions[0]["content"])
        self.assertNotIn("finished", revisions[1]["content"])
        audit_rows = self.client.get(f"/api/experiments/{experiment_id}/audit").get_json()["audit"]
        self.assertEqual([row["action"] for row in audit_rows], ["create", "update"])
        self.assertEqual(audit_rows[-1]["detail"], "content,status")

    def test_other_member_cannot_read_revisions(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.pi)
        self.assertEqual(
            self.client.get(f"/api/experiments/{experiment_id}/revisions").status_code,
            404,
        )

    def test_sign_requires_password_and_binds_revision(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.member)
        wrong = self.client.post(
            f"/api/experiments/{experiment_id}/sign",
            json={"password": "wrong", "meaning": "author"},
        )
        self.assertEqual(wrong.status_code, 401)
        signed = self.client.post(
            f"/api/experiments/{experiment_id}/sign",
            json={"password": "long-enough-password", "meaning": "author"},
        )
        self.assertEqual(signed.status_code, 201)
        signature = signed.get_json()
        self.assertEqual(signature["revision"], 1)
        self.assertEqual(signature["signer_user_id"], self.member["user_id"])
        rows = self.client.get(f"/api/experiments/{experiment_id}/signatures").get_json()["signatures"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["record_hash"]), 64)

    def test_non_owner_cannot_sign(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.pi)
        self.assertEqual(
            self.client.post(
                f"/api/experiments/{experiment_id}/sign",
                json={"password": "long-enough-password"},
            ).status_code,
            404,
        )


    def test_workspace_request_list_for_pi_and_owner(self) -> None:
        experiment_id = self.create_experiment()
        self.login(self.pi)
        request_id = self.client.post(
            f"/api/experiments/{experiment_id}/access-requests"
        ).get_json()["request_id"]
        pi_rows = self.client.get("/api/experiment-access-requests").get_json()["requests"]
        self.assertEqual([row["request_id"] for row in pi_rows], [request_id])
        self.assertEqual(pi_rows[0]["experiment_title"], "Run")
        self.login(self.member)
        owner_rows = self.client.get("/api/experiment-access-requests").get_json()["requests"]
        self.assertEqual([row["request_id"] for row in owner_rows], [request_id])


if __name__ == "__main__":
    unittest.main()
