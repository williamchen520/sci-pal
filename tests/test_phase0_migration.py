from __future__ import annotations

import unittest
from pathlib import Path

from scripts.apply_pg_migration import statements
from scripts.backfill_phase0 import TABLES, _quote

MIGRATION = Path("build_db/migrations/20261102_phase0_parity.sql")


class Phase0MigrationTests(unittest.TestCase):
    def test_statements_skip_transaction(self):
        parts = statements(MIGRATION.read_text(encoding="utf-8"))
        self.assertEqual(len(parts), 25)
        self.assertTrue(all(not part.upper().startswith(("BEGIN", "COMMIT")) for part in parts))

    def test_migration_covers_phase0_tables(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        for table in TABLES:
            if table == "experiment_runs":
                self.assertIn("ALTER TABLE experiment_runs", sql)
            else:
                self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)

    def test_quote_identifier(self):
        self.assertEqual(_quote('a"b'), '"a""b"')


if __name__ == "__main__":
    unittest.main()
