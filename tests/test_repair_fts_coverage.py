from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.repair_fts_coverage import repair


class RepairFtsCoverageTests(unittest.TestCase):
    def _db(self, tmp: Path) -> Path:
        path = tmp / "research.db"
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE paragraphs (
              para_id TEXT PRIMARY KEY, paper_id TEXT, section_level1 TEXT,
              section_level2 TEXT, text TEXT
            );
            CREATE VIRTUAL TABLE paragraphs_fts USING fts5(
              para_id UNINDEXED, paper_id UNINDEXED, section_l1, section_l2, text
            );
            CREATE TABLE summaries (
              summary_id TEXT PRIMARY KEY, paper_id TEXT, section_id TEXT,
              title TEXT, text TEXT
            );
            CREATE VIRTUAL TABLE summaries_fts USING fts5(
              summary_id, paper_id, section_id, title, text
            );
            INSERT INTO paragraphs VALUES ('p1','paper1','Intro','','Alpha text');
            INSERT INTO paragraphs VALUES ('p2','paper1','Intro','','Beta text');
            INSERT INTO paragraphs_fts VALUES ('p1','paper1','Intro','','Alpha text');
            INSERT INTO summaries VALUES ('s1','paper1','sec1','Title','Summary one');
            INSERT INTO summaries VALUES ('s2','paper1','sec2','Title','Summary two');
            INSERT INTO summaries_fts VALUES ('s1','paper1','sec1','Title','Summary one');
            """
        )
        conn.commit()
        conn.close()
        return path

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._db(Path(tmp))
            result = repair(path)
            self.assertFalse(result["applied"])
            self.assertEqual(result["missing_before"]["paragraphs"], 1)
            self.assertEqual(result["missing_after"]["summaries"], 1)

    def test_apply_repairs_and_installs_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._db(Path(tmp))
            result = repair(path, apply=True)
            self.assertEqual(result["missing_after"], {"paragraphs": 0, "summaries": 0})
            self.assertEqual(result["summaries_triggers"], ["summaries_ad", "summaries_ai", "summaries_au"])
            conn = sqlite3.connect(path)
            conn.execute("INSERT INTO summaries VALUES ('s3','paper1','sec3','Title','Summary three')")
            conn.commit()
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM summaries_fts WHERE summary_id='s3'").fetchone()[0],
                1,
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
