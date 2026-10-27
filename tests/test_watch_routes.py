"""Watch HTTP routes: profile CRUD, journals, read state."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from build_db.watch_schema import migrate
from routes.watch import build_watch_blueprint
from services.watch import repo


class WatchRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, filename TEXT NOT NULL, "
            "title TEXT, authors TEXT, abstract TEXT, journal TEXT, year INTEGER, doi TEXT, "
            "parse_status TEXT, parse_engine TEXT, acquisition TEXT, "
            "created_at TEXT, updated_at TEXT)"
        )
        conn.commit()
        conn.close()
        migrate(self.db)
        app = Flask(__name__)
        app.register_blueprint(build_watch_blueprint(db_path=self.db, log=app.logger))
        self.client = app.test_client()

    def test_profile_crud_and_journals(self) -> None:
        created = self.client.post(
            "/api/watch/profiles",
            json={"name": "HCC", "field_text": "hepatocellular carcinoma"},
        )
        self.assertEqual(created.status_code, 201)
        profile_id = created.get_json()["profile_id"]

        listing = self.client.get("/api/watch/profiles").get_json()["profiles"]
        self.assertEqual(len(listing), 1)

        updated = self.client.put(
            f"/api/watch/profiles/{profile_id}", json={"max_items": 5}
        )
        self.assertEqual(updated.get_json()["max_items"], 5)

        self.client.put(
            f"/api/watch/profiles/{profile_id}/journals",
            json={"journals": [{"issn_l": "1234-5678", "name": "J1"}]},
        )
        journals = self.client.get(
            f"/api/watch/profiles/{profile_id}/journals"
        ).get_json()["journals"]
        self.assertEqual(journals[0]["issn_l"], "1234-5678")

    def test_read_item(self) -> None:
        conn = repo.connect(self.db)
        profile_id = repo.create_profile(conn, {"name": "P"})
        run_id = repo.create_run(conn, profile_id, "2026-10-20", "2026-10-27")
        item_id = repo.add_item(
            conn, run_id, profile_id, {"title": "T", "acquisition": "abstract"}
        )
        conn.close()
        self.assertEqual(
            self.client.post(f"/api/watch/items/{item_id}/read").status_code, 200
        )
        conn = repo.connect(self.db)
        status = conn.execute(
            "SELECT status FROM watch_items WHERE id = ?", (item_id,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(status, "read")


if __name__ == "__main__":
    unittest.main()
