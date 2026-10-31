"""P4 metadata dual-write tests (outbox/triggers, no PostgreSQL required)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.db.dual_write import install, outbox_stats, replay


class FakePG:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, tuple(params or ())))
        return self

    def commit(self):
        pass

    def rollback(self):
        pass


class DualWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        self.conn = sqlite3.connect(self.db)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT);
            CREATE TABLE memberships (
              workspace_id TEXT, user_id TEXT, role TEXT,
              PRIMARY KEY (workspace_id, user_id)
            );
            CREATE TABLE citations (citation_id TEXT PRIMARY KEY, year INTEGER);
            CREATE VIRTUAL TABLE paragraphs_fts USING fts5(para_id UNINDEXED, text);
            """
        )
        self.conn.commit()
        self.report = install(self.conn, ["papers", "memberships", "citations", "paragraphs_fts"])

    def tearDown(self) -> None:
        self.conn.close()

    def test_installs_only_metadata_tables(self) -> None:
        self.assertEqual(self.report["installed"], ["papers", "memberships", "citations"])
        triggers = {
            row[0]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
        self.assertIn("dualwrite_papers_ai", triggers)
        self.assertFalse(any("fts" in name for name in triggers))

    def test_insert_update_delete_enqueue_keys(self) -> None:
        self.conn.execute("INSERT INTO papers VALUES ('p1','One')")
        self.conn.execute("UPDATE papers SET title='Two' WHERE paper_id='p1'")
        self.conn.execute("DELETE FROM papers WHERE paper_id='p1'")
        rows = self.conn.execute(
            "SELECT op, key_json FROM dual_write_outbox ORDER BY id"
        ).fetchall()
        self.assertEqual([row[0] for row in rows], ["upsert", "upsert", "delete"])
        self.assertEqual(json.loads(rows[0][1]), {"paper_id": "p1"})

    def test_composite_key(self) -> None:
        self.conn.execute("INSERT INTO memberships VALUES ('w1','u1','owner')")
        row = self.conn.execute("SELECT key_json FROM dual_write_outbox").fetchone()
        self.assertEqual(json.loads(row[0]), {"workspace_id": "w1", "user_id": "u1"})

    def test_replay_upsert_and_delete(self) -> None:
        self.conn.execute("INSERT INTO papers VALUES ('p1','One')")
        self.conn.commit()
        pg = FakePG()
        result = replay(self.conn, pg, limit=10)
        self.assertEqual(result["applied"], 1)
        self.assertIn('INSERT INTO "papers"', pg.calls[0][0])
        self.assertEqual(pg.calls[0][1], ("p1", "One"))

        self.conn.execute("DELETE FROM papers WHERE paper_id='p1'")
        self.conn.commit()
        pg = FakePG()
        replay(self.conn, pg, limit=10)
        self.assertIn('DELETE FROM "papers"', pg.calls[0][0])
        self.assertEqual(outbox_stats(self.conn)["pending"], 0)

    def test_citation_year_is_stringified(self) -> None:
        self.conn.execute("INSERT INTO citations VALUES ('c1','2020')")
        self.conn.commit()
        pg = FakePG()
        replay(self.conn, pg, limit=10)
        self.assertEqual(pg.calls[0][1], ("c1", "2020"))


if __name__ == "__main__":
    unittest.main()
