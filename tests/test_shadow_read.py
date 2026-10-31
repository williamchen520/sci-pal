"""P3 shadow-read tests using two SQLite databases (no PG server needed)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.db.shadow_read import ShadowReader


class ShadowReadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.left = Path(self.tmp.name) / "left.db"
        self.right = Path(self.tmp.name) / "right.db"
        for path in (self.left, self.right):
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT)")
            conn.executemany(
                "INSERT INTO papers VALUES (?, ?)",
                [("p1", "One"), ("p2", "Two"), ("p3", "Three")],
            )
            conn.commit()
            conn.close()
        self.pg = sqlite3.connect(self.right)
        self.addCleanup(self.pg.close)

    def test_equal_databases_are_ok(self) -> None:
        report = ShadowReader(self.left, self.pg, pg_placeholder="?").run(
            [("papers", "paper_id")], limit=2
        )
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["tables"][0]["compared"], 2)

    def test_field_diff_is_reported(self) -> None:
        self.pg.execute("UPDATE papers SET title='Changed' WHERE paper_id='p1'")
        self.pg.commit()
        diff = ShadowReader(self.left, self.pg, pg_placeholder="?").compare_table(
            "papers", "paper_id", limit=10
        )
        self.assertEqual(diff.status, "diff")
        self.assertEqual(diff.field_diffs, 1)
        self.assertEqual(diff.samples[0]["fields"], ["title"])

    def test_missing_row_is_reported(self) -> None:
        self.pg.execute("DELETE FROM papers WHERE paper_id='p3'")
        self.pg.commit()
        diff = ShadowReader(self.left, self.pg, pg_placeholder="?").compare_table(
            "papers", "paper_id", limit=10
        )
        self.assertEqual(diff.missing_in_pg, 1)

    def test_count_mismatch_is_reported(self) -> None:
        self.pg.execute("INSERT INTO papers VALUES ('p4','Four')")
        self.pg.commit()
        diff = ShadowReader(self.left, self.pg, pg_placeholder="?").compare_table(
            "papers", "paper_id", limit=10
        )
        self.assertEqual(diff.extra_in_pg, 1)
        self.assertEqual(diff.sqlite_rows, 3)
        self.assertEqual(diff.postgres_rows, 4)


if __name__ == "__main__":
    unittest.main()
