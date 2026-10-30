"""Watch scheduler: due profile selection and batch isolation."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_db.watch_schema import migrate
from services.watch import repo, scheduler


class WatchSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "watch.db"
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
        conn = repo.connect(self.db)
        self.due = repo.create_profile(conn, {"name": "due"})
        self.future = repo.create_profile(conn, {"name": "future"})
        conn.execute(
            "UPDATE watch_profiles SET next_run_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), self.due),
        )
        conn.execute(
            "UPDATE watch_profiles SET next_run_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), self.future),
        )
        conn.commit()
        conn.close()

    def test_due_profiles_skips_future_and_disabled(self) -> None:
        conn = repo.connect(self.db)
        try:
            self.assertEqual(
                [row["id"] for row in scheduler.due_profiles(conn)],
                [self.due],
            )
            conn.execute("UPDATE watch_profiles SET enabled = 0 WHERE id = ?", (self.due,))
            conn.commit()
            self.assertEqual(scheduler.due_profiles(conn), [])
        finally:
            conn.close()

    def test_run_due_continues_after_failure(self) -> None:
        conn = repo.connect(self.db)
        conn.execute(
            "UPDATE watch_profiles SET next_run_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), self.future),
        )
        conn.commit()
        conn.close()
        calls = []

        def fake_run(db_path, profile_id):
            calls.append(profile_id)
            if profile_id == self.due:
                raise RuntimeError("boom")
            return {"run_id": 1}

        results = scheduler.run_due(self.db, run_profile=fake_run)
        self.assertEqual(calls, [self.due, self.future])
        self.assertFalse(results[0]["ok"])
        self.assertIn("boom", results[0]["error"])
        self.assertTrue(results[1]["ok"])


if __name__ == "__main__":
    unittest.main()
