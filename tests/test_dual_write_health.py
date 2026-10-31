"""P4 dual-write health check tests (SQLite as the PG stub)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.dual_write_healthcheck import collect
from services.db.dual_write import install


class HealthCheckTests(unittest.TestCase):
    def test_reports_pending_and_count_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            left = Path(tmp) / "left.db"
            right = Path(tmp) / "right.db"
            for path in (left, right):
                conn = sqlite3.connect(path)
                conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT)")
                conn.commit()
                conn.close()
            conn = sqlite3.connect(left)
            install(conn, ["papers"])
            conn.execute("INSERT INTO papers VALUES ('p1','One')")
            conn.commit()
            pg = sqlite3.connect(right)
            try:
                report = collect(conn, pg, ["papers"])
            finally:
                pg.close()
                conn.close()
            self.assertEqual(report["pending"], 1)
            self.assertEqual(report["triggers"], 3)
            self.assertEqual(report["mismatches"], ["papers"])


if __name__ == "__main__":
    unittest.main()
