from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.db import sqlite_readonly


class SQLiteReadonlyTests(unittest.TestCase):
    def tearDown(self):
        sqlite3.connect = sqlite_readonly._ORIGINAL_CONNECT
        sqlite_readonly._INSTALLED = False

    def test_blocks_writes_for_research_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "research.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.commit()
            conn.close()
            with mock.patch.dict(
                os.environ, {"SCIPAL_SQLITE_QUERY_ONLY": "1"}, clear=False
            ):
                self.assertTrue(sqlite_readonly.install())
                conn = sqlite3.connect(db)
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("INSERT INTO t (id) VALUES (1)")
                conn.close()

    def test_other_db_not_guarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "other.db"
            with mock.patch.dict(
                os.environ, {"SCIPAL_SQLITE_QUERY_ONLY": "1"}, clear=False
            ):
                sqlite_readonly.install()
                conn = sqlite3.connect(db)
                conn.execute("CREATE TABLE t (id INTEGER)")
                conn.commit()
                conn.close()


if __name__ == "__main__":
    unittest.main()
