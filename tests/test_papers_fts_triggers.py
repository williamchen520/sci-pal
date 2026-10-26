"""papers_fts triggers (insert/update/delete stay in sync with papers)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.build_fts import rebuild_papers_triggers


class PapersTriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY, title TEXT, authors TEXT,
                journal TEXT, filename TEXT, abstract TEXT, parse_engine TEXT
            );
            CREATE VIRTUAL TABLE papers_fts USING fts5(
                paper_id UNINDEXED, title, authors, journal,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            """
        )
        rebuild_papers_triggers(conn)
        conn.commit()
        self.conn = conn
        self.addCleanup(conn.close)

    def _count(self, term: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM papers_fts WHERE papers_fts MATCH ?", (term,)
        ).fetchone()[0]

    def test_insert_is_indexed(self) -> None:
        self.conn.execute(
            "INSERT INTO papers (paper_id, title, authors, journal) VALUES ('p1','Sepsis TLR4','A','J')"
        )
        self.conn.commit()
        self.assertEqual(self._count("sepsis"), 1)

    def test_update_reindexes(self) -> None:
        self.conn.execute(
            "INSERT INTO papers (paper_id, title, authors, journal) VALUES ('p1','Old title','A','J')"
        )
        self.conn.commit()
        self.conn.execute("UPDATE papers SET title='New sepsis title' WHERE paper_id='p1'")
        self.conn.commit()
        self.assertEqual(self._count("old"), 0)
        self.assertEqual(self._count("sepsis"), 1)

    def test_delete_removes_index_entry(self) -> None:
        self.conn.execute(
            "INSERT INTO papers (paper_id, title, authors, journal) VALUES ('p1','Sepsis','A','J')"
        )
        self.conn.commit()
        self.conn.execute("DELETE FROM papers WHERE paper_id='p1'")
        self.conn.commit()
        self.assertEqual(self._count("sepsis"), 0)


if __name__ == "__main__":
    unittest.main()
