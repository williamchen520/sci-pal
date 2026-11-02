from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.watch import pg_writes


class WatchPGWritesTests(unittest.TestCase):
    def test_enabled_flag(self):
        with mock.patch.dict(
            os.environ,
            {"SCIPAL_WATCH_WRITE_BACKEND": "postgres", "SCIPAL_PG_DSN": "postgresql://x"},
            clear=False,
        ):
            self.assertTrue(pg_writes.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_WRITE_BACKEND": ""}, clear=False):
            self.assertFalse(pg_writes.enabled())

    def test_disabled_does_not_touch_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO papers VALUES ('p1')")
            conn.commit()
            conn.close()
            with mock.patch.object(pg_writes, "enabled", return_value=False):
                self.assertFalse(pg_writes.delete_paper_best_effort("p1", db_path=db))
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(conn.execute("SELECT count(*) FROM papers").fetchone()[0], 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
