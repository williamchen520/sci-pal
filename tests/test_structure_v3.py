"""Structure v3: section paths, indexes, sentence FTS."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.structure_v3 import migrate


class StructureV3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE sections (section_id TEXT PRIMARY KEY, paper_id TEXT,
                parent_id TEXT, level INTEGER, title TEXT, seq INTEGER, source TEXT);
            CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT,
                section_id TEXT, text TEXT, sequence INTEGER, page INTEGER);
            CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, para_id TEXT,
                paper_id TEXT, section_id TEXT, text TEXT, sequence INTEGER,
                page INTEGER, bbox TEXT);
            CREATE TABLE figures (fig_id TEXT PRIMARY KEY, paper_id TEXT, fig_number TEXT);
            CREATE TABLE tables (table_id TEXT PRIMARY KEY, paper_id TEXT, table_number TEXT);
            CREATE TABLE citations (citation_id TEXT PRIMARY KEY, paper_id TEXT, ref_number TEXT);
            """
        )
        conn.execute("INSERT INTO sections VALUES ('s1','p1',NULL,1,'Results',1,'jats')")
        conn.execute("INSERT INTO sections VALUES ('s2','p1','s1',2,'Efficacy',2,'jats')")
        conn.execute("INSERT INTO sections VALUES ('s3','p1','s2',3,'Subgroup',3,'jats')")
        conn.execute(
            "INSERT INTO paragraphs VALUES ('para1','p1','s3','Response rate was 42%.',1,3)"
        )
        conn.execute(
            "INSERT INTO sentences VALUES ('sent1','para1','p1','s3',"
            "'Response rate was 42%.',1,3,'10,20,100,40')"
        )
        conn.commit()
        conn.close()

    def test_paths_and_fts(self) -> None:
        stats = migrate(self.db)
        self.assertEqual(stats["paths"], 3)
        conn = sqlite3.connect(self.db)
        rows = conn.execute(
            "SELECT section_id, path, depth FROM sections ORDER BY seq"
        ).fetchall()
        self.assertEqual(rows, [("s1", "1", 1), ("s2", "1.1", 2), ("s3", "1.1.1", 3)])
        match = conn.execute(
            "SELECT sentence_id FROM sentences_fts WHERE sentences_fts MATCH 'response'"
        ).fetchall()
        self.assertEqual([r[0] for r in match], ["sent1"])
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(sections)")}
        self.assertIn("idx_sections_path", indexes)
        conn.close()

    def test_idempotent(self) -> None:
        migrate(self.db)
        migrate(self.db)
        conn = sqlite3.connect(self.db)
        self.assertEqual(
            conn.execute("SELECT path FROM sections WHERE section_id='s3'").fetchone()[0],
            "1.1.1",
        )
        conn.close()


if __name__ == "__main__":
    unittest.main()
