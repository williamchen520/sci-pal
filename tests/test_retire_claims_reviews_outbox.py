from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.retire_claims_reviews_outbox import retire
from services.db.dual_write import install


class RetireClaimsReviewsOutboxTests(unittest.TestCase):
    def test_drops_triggers_and_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE claim_cards (claim_id TEXT PRIMARY KEY, title TEXT)")
            install(conn, ["claim_cards"])
            conn.execute("INSERT INTO claim_cards VALUES ('c1','t')")
            conn.commit()
            conn.close()
            report = retire(db)
            self.assertEqual(len(report["dropped"]), 3)
            self.assertEqual(report["remaining_triggers"], [])
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
            conn.execute("CREATE TABLE claim_cards (claim_id TEXT PRIMARY KEY, title TEXT)")
            install(conn, ["claim_cards"])
            conn.commit()
            conn.close()
            report = retire(db, dry_run=True)
            self.assertGreater(len(report["dropped"]), 0)
            conn = sqlite3.connect(db)
            try:
                self.assertEqual(
                    conn.execute(
                        "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'dualwrite_claim_cards_%'"
                    ).fetchone()[0],
                    3,
                )
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
