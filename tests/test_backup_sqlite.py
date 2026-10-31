"""SQLite backup safety tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.backup_sqlite import create_backup


class BackupSQLiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "research.db"
        conn = sqlite3.connect(self.source)
        conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO papers VALUES ('p1')")
        conn.commit()
        conn.close()

    def test_backup_is_verified_and_source_unchanged(self) -> None:
        result = create_backup(self.source, self.root / "backups")
        self.assertEqual(result["backup_integrity"], "ok")
        self.assertEqual(result["papers"], 1)
        self.assertNotEqual(Path(result["dest"]), self.source)
        conn = sqlite3.connect(self.source)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
