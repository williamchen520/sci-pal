"""JATS parser + structured importer (temp DB, no network)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.import_jats import import_file
from build_db.jats_parser import parse_jats
from build_db.structure_v2 import migrate

SAMPLE = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front>
    <article-meta>
      <title-group><article-title>A test article</article-title></title-group>
      <article-id pub-id-type="doi">10.1234/test.1</article-id>
      <pub-date><year>2026</year></pub-date>
      <abstract><p>Abstract text.</p></abstract>
    </article-meta>
    <journal-meta><journal-title>Test Journal</journal-title></journal-meta>
  </front>
  <body>
    <sec id="s1"><title>Introduction</title>
      <p>Intro text with a citation <xref ref-type="bibr" rid="R1">[1]</xref>.</p>
      <sec id="s1-1"><title>Background</title>
        <p>Nested paragraph with a figure <xref ref-type="fig" rid="F1">Fig 1</xref>.</p>
      </sec>
    </sec>
    <sec id="s2"><title>Methods</title>
      <p>Methods text.</p>
    </sec>
  </body>
  <floats-group>
    <fig id="F1"><label>Fig 1</label><caption>Figure caption.</caption></fig>
    <table-wrap id="T1"><label>Table 1</label><caption>Table caption.</caption></table-wrap>
  </floats-group>
  <back>
    <ref-list>
      <ref id="R1"><mixed-citation>Smith J. A paper. 2020. doi:10.9999/x</mixed-citation></ref>
    </ref-list>
  </back>
</article>
"""


def make_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE papers (
            paper_id TEXT PRIMARY KEY, filename TEXT, title TEXT, authors TEXT,
            abstract TEXT, journal TEXT, year TEXT, doi TEXT, keywords TEXT,
            parse_status TEXT, parse_engine TEXT, total_paragraphs INTEGER,
            total_figures INTEGER, total_tables INTEGER, total_citations INTEGER,
            updated_at TEXT
        );
        CREATE TABLE paragraphs (
            para_id TEXT PRIMARY KEY, paper_id TEXT, section_level1 TEXT,
            section_level2 TEXT, section_level3 TEXT, text TEXT, sequence INTEGER,
            page INTEGER, bbox TEXT
        );
        CREATE TABLE citations (
            citation_id TEXT PRIMARY KEY, paper_id TEXT, ref_number TEXT,
            raw_text TEXT, doi TEXT, title TEXT, authors TEXT, journal TEXT, year TEXT
        );
        CREATE TABLE figures (
            fig_id TEXT PRIMARY KEY, paper_id TEXT, fig_number TEXT, caption TEXT,
            file_path TEXT, page INTEGER, bbox TEXT
        );
        CREATE TABLE tables (
            table_id TEXT PRIMARY KEY, paper_id TEXT, table_number TEXT,
            caption TEXT, markdown TEXT
        );
        CREATE TABLE sentences (
            sentence_id TEXT PRIMARY KEY, para_id TEXT, paper_id TEXT,
            text TEXT, sequence INTEGER
        );
        CREATE TABLE sentence_links (
            link_id TEXT PRIMARY KEY, sentence_id TEXT, para_id TEXT, paper_id TEXT,
            source_type TEXT, target_type TEXT, target_id TEXT, relation TEXT
        );
        CREATE TABLE cross_paper_index (link_id TEXT, source_paper_id TEXT,
            target_paper_id TEXT, relation TEXT, confidence REAL);
        CREATE TABLE paper_index (index_id TEXT);
        CREATE TABLE full_citation_edges (id INTEGER);
        """
    )
    migrate(path)
    return conn


class JatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.xml = self.dir / "PMC1.xml"
        self.xml.write_text(SAMPLE, encoding="utf-8")

    def test_parser_structure(self) -> None:
        data = parse_jats(SAMPLE)
        self.assertEqual(data["metadata"]["title"], "A test article")
        self.assertEqual(data["metadata"]["doi"], "10.1234/test.1")
        self.assertEqual(len(data["sections"]), 3)
        nested = [s for s in data["sections"] if s["level"] == 2][0]
        self.assertEqual(nested["title"], "Background")
        self.assertTrue(nested["parent_id"])
        refs = data["references"]
        self.assertEqual(refs[0]["id"], "R1")
        self.assertEqual(refs[0]["doi"], "10.9999/x")
        xrefs = [x for p in data["paragraphs"] for x in p["xrefs"]]
        self.assertEqual({x["ref_type"] for x in xrefs}, {"bibr", "fig"})

    def test_import_writes_structured_rows(self) -> None:
        db = self.dir / "t.db"
        conn = make_db(db)
        stats = import_file(conn, self.xml, paper_id="paper1")
        conn.commit()
        self.assertEqual(stats["sections"], 3)
        self.assertEqual(stats["citations"], 1)
        self.assertEqual(stats["figures"], 1)
        self.assertEqual(stats["tables"], 1)
        self.assertGreater(stats["sentences"], 0)
        self.assertEqual(stats["links"], 2)

        levels = [r[0] for r in conn.execute("SELECT level FROM sections ORDER BY seq")]
        self.assertEqual(levels, [1, 2, 1])
        parent = conn.execute(
            "SELECT parent_id FROM sections WHERE title='Background'"
        ).fetchone()[0]
        self.assertTrue(parent.startswith("paper1_sec_"))
        links = conn.execute(
            "SELECT source, confidence, target_type FROM sentence_links ORDER BY target_type"
        ).fetchall()
        self.assertEqual(len(links), 2)
        self.assertTrue(all(row[0] == "jats" and row[1] == 1.0 for row in links))
        self.assertEqual({row[2] for row in links}, {"citation", "figure"})
        conn.close()


if __name__ == "__main__":
    unittest.main()
