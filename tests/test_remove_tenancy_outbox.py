from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.remove_tenancy_outbox import remove
from services.db.dual_write import install


class RemoveTenancyOutboxTests(unittest.TestCase):
    def test_drops_triggers_and_pending_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT)")
            install(conn, ["users"])
            conn.execute("INSERT INTO users VALUES ('u1', 'alice')")
            conn.commit()
            conn.close()
            report = remove(db)
            self.assertEqual(len(report["dropped"]), 3)
            self.assertEqual(report["remaining_tenancy_triggers"], [])
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(
                    conn.execute(
                        "SELECT count(*) FROM dual_write_outbox WHERE processed_at IS NULL"
                    ).fetchone()[0],
                    0,
                )
            finally:
                conn.close()

    def test_dry_run_keeps_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE users (user_id TEXT PRIMARY KEY, username TEXT)")
            install(conn, ["users"])
            conn.commit()
            conn.close()
            report = remove(db, dry_run=True)
            self.assertGreater(len(report["dropped"]), 0)
            conn = sqlite3.connect(db)
            try:
                triggers = conn.execute(
                    "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_users_%'"
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(triggers, 3)


if __name__ == "__main__":
    unittest.main()
