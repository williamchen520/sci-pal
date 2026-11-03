from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.repair_abstract_fts import repair


class RepairAbstractFtsTests(unittest.TestCase):
    def _db(self, tmp: Path) -> Path:
        path = tmp / "abstracts.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE papers (
              id INTEGER PRIMARY KEY, pmid TEXT, doi TEXT, title TEXT, abstract TEXT,
              authors TEXT, journal TEXT, year TEXT, topic TEXT, source TEXT
            );
            CREATE VIRTUAL TABLE papers_fts USING fts5(
              pmid UNINDEXED, title, abstract, authors, journal, topic UNINDEXED
            );
            INSERT INTO papers (pmid,title,abstract,authors,journal,topic) VALUES
              ('1','One','Alpha','A','J','T'), ('2','Two','Beta','B','J','T');
            INSERT INTO papers_fts (pmid,title,abstract,authors,journal,topic)
              VALUES ('1','One','Alpha','A','J','T');
            """
        )
        conn.commit()
        conn.close()
        return path

    def test_apply_fills_and_installs_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._db(Path(tmp))
            result = repair(path, apply=True)
            self.assertEqual(result["missing_before"], 1)
            self.assertEqual(result["after"], {"papers": 2, "papers_fts": 2})
            self.assertEqual(result["triggers"], ["papers_ad", "papers_ai", "papers_au"])
            conn = sqlite3.connect(path)
            conn.execute(
                "INSERT INTO papers (pmid,title,abstract,authors,journal,topic) "
                "VALUES ('3','Three','Gamma','C','J','T')"
            )
            conn.commit()
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM papers_fts WHERE pmid='3'").fetchone()[0], 1
            )
            conn.close()

    def test_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._db(Path(tmp))
            result = repair(path)
            self.assertEqual(result["missing_before"], 1)
            self.assertEqual(result["after"]["papers_fts"], 1)


if __name__ == "__main__":
    unittest.main()
