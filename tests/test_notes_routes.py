"""Notes API workspace isolation."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.notes import build_notes_blueprint
from services.tenancy import create_user, create_workspace


class NotesRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "notes.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, workspace_id TEXT)")
        conn.commit()
        conn.close()
        self.alice = create_user("alice", "long-enough-password", db_path=self.db)
        self.bob = create_user("bob", "long-enough-password", db_path=self.db)
        self.ws_a = create_workspace("A", self.alice["user_id"], db_path=self.db)["workspace_id"]
        self.ws_b = create_workspace("B", self.bob["user_id"], db_path=self.db)["workspace_id"]
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO papers VALUES ('p_a', ?)", (self.ws_a,))
        conn.execute("INSERT INTO papers VALUES ('p_b', ?)", (self.ws_b,))
        conn.commit()
        conn.close()
        app = Flask(__name__)
        app.secret_key = "test"
        app.register_blueprint(build_notes_blueprint(db_path=self.db))
        self.client = app.test_client()

    def login(self, user: dict, workspace_id: str) -> None:
        with self.client.session_transaction() as session:
            session["user_id"] = user["user_id"]
            session["workspace_id"] = workspace_id

    def test_create_and_list(self) -> None:
        self.login(self.alice, self.ws_a)
        created = self.client.post("/api/notes", json={"content": "hello", "paper_id": "p_a"})
        self.assertEqual(created.status_code, 201)
        listed = self.client.get("/api/notes").get_json()["notes"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["content"], "hello")

    def test_cross_workspace_paper_rejected(self) -> None:
        self.login(self.alice, self.ws_a)
        self.assertEqual(
            self.client.post("/api/notes", json={"content": "x", "paper_id": "p_b"}).status_code,
            404,
        )

    def test_cannot_update_other_users_note(self) -> None:
        self.login(self.alice, self.ws_a)
        note_id = self.client.post("/api/notes", json={"content": "mine"}).get_json()["note_id"]
        self.login(self.bob, self.ws_b)
        self.assertEqual(
            self.client.put(f"/api/notes/{note_id}", json={"content": "hacked"}).status_code,
            404,
        )

    def test_list_is_workspace_scoped(self) -> None:
        self.login(self.alice, self.ws_a)
        self.client.post("/api/notes", json={"content": "A"})
        self.login(self.bob, self.ws_b)
        self.assertEqual(self.client.get("/api/notes").get_json()["notes"], [])

    def test_requires_login(self) -> None:
        self.assertEqual(self.client.get("/api/notes").status_code, 401)


if __name__ == "__main__":
    unittest.main()
