"""Structure v2: migrations, section tree, sentence geometry, links, graph sync."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db import structure_v2
from build_db.build_sections_tree import build_for_paper as build_sections
from build_db.rebuild_sentence_links import (
    _mention_bbox_top_left,
    build_for_paper as build_links,
)
from build_db.sentence_geometry import parse_bbox, split_sentences, to_topleft
from build_db.sync_paper_links import sync as sync_links


def make_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE papers (paper_id TEXT, filename TEXT, title TEXT, doi TEXT);
        CREATE TABLE paragraphs (
            para_id TEXT, paper_id TEXT, section_level1 TEXT, section_level2 TEXT,
            section_level3 TEXT, text TEXT, sequence INTEGER, page INTEGER, bbox TEXT
        );
        CREATE TABLE citations (
            citation_id TEXT, paper_id TEXT, ref_number TEXT, raw_text TEXT,
            doi TEXT, title TEXT, authors TEXT, journal TEXT, year TEXT
        );
        CREATE TABLE figures (fig_id TEXT, paper_id TEXT, fig_number TEXT, caption TEXT);
        CREATE TABLE tables (table_id TEXT, paper_id TEXT, table_number TEXT, caption TEXT, markdown TEXT);
        CREATE TABLE sentences (
            sentence_id TEXT PRIMARY KEY, para_id TEXT, paper_id TEXT, text TEXT,
            sequence INTEGER
        );
        CREATE TABLE sentence_links (
            link_id TEXT PRIMARY KEY, sentence_id TEXT, para_id TEXT, paper_id TEXT,
            source_type TEXT, target_type TEXT, target_id TEXT, relation TEXT
        );
        CREATE TABLE citation_mentions (
            mention_id TEXT PRIMARY KEY, paper_id TEXT, ref_number TEXT,
            page INTEGER, bbox TEXT, context TEXT, source TEXT
        );
        CREATE TABLE cross_paper_index (
            link_id TEXT, source_paper_id TEXT, target_paper_id TEXT,
            relation TEXT, confidence REAL
        );
        CREATE TABLE paper_index (
            index_id TEXT, paper_id TEXT, source_type TEXT, source_id TEXT,
            target_type TEXT, target_id TEXT, relation TEXT
        );
        CREATE TABLE full_citation_edges (id INTEGER, source_doi TEXT, target_doi TEXT, source_pmc_id TEXT);
        """
    )
    return conn


class StructureV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        self.conn = make_db(self.db)
        self.addCleanup(self.conn.close)

    def test_migration_adds_columns_and_tables(self) -> None:
        result = structure_v2.migrate(self.db)
        self.assertIn("sentences.bbox", result["added_columns"])
        self.assertIn("paragraphs.section_path", result["added_columns"])
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master")}
        self.assertIn("sections", tables)
        self.assertIn("paper_links", tables)
        # idempotent
        self.assertEqual(structure_v2.migrate(self.db)["added_columns"], [])

    def test_sentence_helpers(self) -> None:
        self.assertEqual(split_sentences("One. Two! Three?"), ["One.", "Two!", "Three?"])
        self.assertEqual(parse_bbox("1,2,3,4"), (1.0, 2.0, 3.0, 4.0))
        self.assertIsNone(parse_bbox("bad"))
        self.assertEqual(to_topleft((10, 90, 20, 80), 100), (10.0, 10.0, 20.0, 20.0))
        self.assertEqual(to_topleft((10, 10, 20, 20), 100), (10, 10, 20, 20))
        self.assertEqual(
            _mention_bbox_top_left("10,80,20,90", 100), "10.00,10.00,20.00,20.00"
        )

    def test_section_tree_parent_links(self) -> None:
        structure_v2.migrate(self.db)
        self.conn.execute(
            "INSERT INTO paragraphs (para_id,paper_id,section_level1,section_level2,section_level3,text,sequence,page,bbox) VALUES (?,?,?,?,?,?,?,?,?)",
            ("p1", "paper1", "body", "Intro", None, "text", 1, 1, "1,1,2,2"),
        )
        self.conn.executemany(
            "UPDATE paragraphs SET section_path = ? WHERE para_id = ?",
            [(json.dumps(["A", "B"]), "p1")],
        )
        self.conn.commit()
        stats = build_sections(self.db, "paper1")
        self.assertEqual(stats["sections"], 2)
        rows = list(
            self.conn.execute("SELECT section_id, parent_id, level FROM sections ORDER BY seq")
        )
        self.assertIsNone(rows[0][1])
        self.assertEqual(rows[1][1], rows[0][0])
        self.assertEqual(rows[1][2], 2)
        bound = self.conn.execute(
            "SELECT section_id FROM paragraphs WHERE para_id='p1'"
        ).fetchone()[0]
        self.assertEqual(bound, rows[1][0])

    def test_sentence_links_carry_page_and_bbox(self) -> None:
        structure_v2.migrate(self.db)
        self.conn.execute(
            "INSERT INTO paragraphs (para_id,paper_id,section_level1,section_level2,section_level3,text,sequence,page,bbox) VALUES (?,?,?,?,?,?,?,?,?)",
            ("p1", "paper1", "body", "Intro", None, "text", 1, 2, "1,1,2,2"),
        )
        self.conn.execute(
            "INSERT INTO citations (citation_id,paper_id,ref_number,raw_text,doi,title,authors,journal,year) VALUES (?,?,?,?,?,?,?,?,?)",
            ("c1", "paper1", "1", "[1]", "10.1/x", "T", "A", "J", "2020"),
        )
        self.conn.execute(
            "INSERT INTO figures (fig_id, paper_id, fig_number, caption) VALUES ('f1','paper1','Fig 1','cap')"
        )
        self.conn.executemany(
            "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence,page,bbox) VALUES (?,?,?,?,?,?,?)",
            [
                ("s1", "p1", "paper1", "We showed [1] and Fig. 1.", 1, 2, "1,1,2,2"),
                ("s2", "p1", "paper1", "No markers here.", 2, 2, "1,1,2,2"),
            ],
        )
        self.conn.commit()
        stats = build_links(self.db, "paper1")
        self.assertEqual(stats["citations"], 1)
        self.assertEqual(stats["figures"], 1)
        row = self.conn.execute(
            "SELECT page, bbox, source, confidence FROM sentence_links "
            "WHERE target_type='citation'"
        ).fetchone()
        self.assertEqual(row[0], 2)
        self.assertEqual(row[1], "1,1,2,2")
        self.assertEqual(row[2], "regex")
        self.assertAlmostEqual(row[3], 0.6)

    def test_links_use_grobid_mention_bbox(self) -> None:
        structure_v2.migrate(self.db)
        self.conn.execute(
            "INSERT INTO papers VALUES ('paper1','a.pdf','T','10.1/a')"
        )
        self.conn.execute(
            "INSERT INTO paragraphs (para_id,paper_id,section_level1,section_level2,section_level3,text,sequence,page,bbox) VALUES (?,?,?,?,?,?,?,?,?)",
            ("p1", "paper1", "body", "", None, "text", 1, 1, "0,0,10,10"),
        )
        self.conn.execute(
            "INSERT INTO citations (citation_id,paper_id,ref_number,raw_text) VALUES ('c1','paper1','1','[1]')"
        )
        self.conn.execute(
            "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence) VALUES ('s1','p1','paper1','See [1].',1)"
        )
        self.conn.execute(
            "INSERT INTO citation_mentions (mention_id,paper_id,ref_number,page,bbox,context,source) VALUES "
            "('m1','paper1','1',1,'10,80,20,90','[1]','grobid')"
        )
        self.conn.commit()
        build_links(self.db, "paper1")
        row = self.conn.execute(
            "SELECT source, confidence, page FROM sentence_links WHERE target_type='citation'"
        ).fetchone()
        self.assertEqual(row[0], "grobid")
        self.assertAlmostEqual(row[1], 0.9)
        self.assertEqual(row[2], 1)

    def test_sync_paper_links(self) -> None:
        structure_v2.migrate(self.db)
        self.conn.execute("INSERT INTO papers VALUES ('p1','a.pdf','A','10.1/a')")
        self.conn.execute("INSERT INTO papers VALUES ('p2','b.pdf','B','10.1/b')")
        self.conn.execute(
            "INSERT INTO cross_paper_index VALUES ('l1','p1','p2','similar',0.8)"
        )
        self.conn.execute(
            "INSERT INTO paper_index VALUES ('i1','p1','paper','p1','paper','10.1/b','cites')"
        )
        self.conn.execute(
            "INSERT INTO citations (citation_id,paper_id,ref_number,raw_text,doi) VALUES ('c1','p1','1','[1]','10.1/b')"
        )
        self.conn.commit()
        stats = sync_links(self.db)
        self.assertGreaterEqual(stats["links"], 2)
        relations = {r[0] for r in self.conn.execute("SELECT relation FROM paper_links")}
        self.assertIn("similar", relations)
        self.assertIn("cites", relations)
        resolved = self.conn.execute(
            "SELECT COUNT(*) FROM paper_links WHERE target_paper_id='p2'"
        ).fetchone()[0]
        self.assertGreaterEqual(resolved, 1)


if __name__ == "__main__":
    unittest.main()
