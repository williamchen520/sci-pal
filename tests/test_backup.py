from __future__ import annotations

import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path

from deploy.backup import create_archive
from scripts.verify_backup import restore_archive, verify_archive


class BackupTests(unittest.TestCase):
    def _data(self, tmp: Path) -> Path:
        data = tmp / "data"
        data.mkdir()
        conn = sqlite3.connect(data / "research.db")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE papers (paper_id TEXT)")
        conn.execute("INSERT INTO papers VALUES ('p1')")
        conn.commit()
        conn.close()
        (data / "note.txt").write_text("note", encoding="utf-8")
        return data

    def test_archive_contains_one_research_db_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self._data(root)
            archive = create_archive(data, root / "backups")
            with tarfile.open(archive) as tar:
                names = [m.name for m in tar.getmembers()]
            self.assertEqual(names.count("data/research.db"), 1)
            self.assertIn("data/note.txt", names)
            result = verify_archive(archive, expected_papers=1)
            self.assertTrue(result["ok"])
            self.assertEqual(result["papers"], 1)

    def test_db_scope_contains_only_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = create_archive(self._data(root), root / "backups", scope="db")
            with tarfile.open(archive) as tar:
                names = [m.name for m in tar.getmembers()]
            self.assertEqual(names, ["data/research.db"])
            self.assertTrue(verify_archive(archive, expected_papers=1)["ok"])

    def test_restore_writes_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = create_archive(self._data(root), root / "backups")
            target = root / "restore" / "research.db"
            restore_archive(archive, target)
            conn = sqlite3.connect(target)
            try:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0], 1)
            finally:
                conn.close()

    def test_restore_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = create_archive(self._data(root), root / "backups")
            target = root / "research.db"
            target.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                restore_archive(archive, target)


if __name__ == "__main__":
    unittest.main()
