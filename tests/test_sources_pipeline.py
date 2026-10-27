"""Batch sources, preprint ingest, metadata backfill, JATS figure fallback."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from build_db import backfill_metadata
from build_db import import_jats
from build_db.jats_parser import parse_jats
from services.search import europe_pmc_batch, preprint_ingest

FALLBACK_XML = """<article><front><article-meta>
<title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Results</title>
<p>As shown in Fig 1 the effect is large.</p>
<p>Table 2 lists the cohorts.</p>
</sec></body>
<floats-group>
<fig id="F1"><label>Fig 1</label><caption>c</caption></fig>
<table-wrap id="T2"><label>Table 2</label><caption>c</caption></table-wrap>
</floats-group></article>"""


def make_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE papers (paper_id TEXT PRIMARY KEY, filename TEXT, title TEXT,
            authors TEXT, abstract TEXT, journal TEXT, year TEXT, doi TEXT,
            keywords TEXT, parse_status TEXT, parse_engine TEXT, total_paragraphs INTEGER,
            total_figures INTEGER, total_tables INTEGER, total_citations INTEGER,
            updated_at TEXT);
        CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT,
            section_level1 TEXT, section_level2 TEXT, section_level3 TEXT, text TEXT,
            sequence INTEGER, page INTEGER, bbox TEXT);
        CREATE TABLE citations (citation_id TEXT PRIMARY KEY, paper_id TEXT,
            ref_number TEXT, raw_text TEXT, doi TEXT, title TEXT, authors TEXT,
            journal TEXT, year TEXT);
        CREATE TABLE figures (fig_id TEXT PRIMARY KEY, paper_id TEXT, fig_number TEXT,
            caption TEXT, file_path TEXT, page INTEGER, bbox TEXT);
        CREATE TABLE tables (table_id TEXT PRIMARY KEY, paper_id TEXT, table_number TEXT,
            caption TEXT, markdown TEXT);
        CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, para_id TEXT, paper_id TEXT,
            text TEXT, sequence INTEGER);
        CREATE TABLE sentence_links (link_id TEXT PRIMARY KEY, sentence_id TEXT,
            para_id TEXT, paper_id TEXT, source_type TEXT, target_type TEXT,
            target_id TEXT, relation TEXT);
        CREATE TABLE paper_links (link_id TEXT, source_paper_id TEXT, target_paper_id TEXT,
            target_doi TEXT, relation TEXT, evidence_sentence_id TEXT, source TEXT,
            confidence REAL);
        """
    )
    from build_db.structure_v2 import migrate

    migrate(path)
    return conn


class JatsFallbackTests(unittest.TestCase):
    def test_regex_fallback_for_fig_and_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            xml = Path(tmp) / "PMC9.xml"
            xml.write_text(FALLBACK_XML, encoding="utf-8")
            conn = make_db(db)
            stats = import_jats.import_file(conn, xml, paper_id="p1")
            conn.commit()
            self.assertEqual(stats["links"], 2)
            rows = conn.execute(
                "SELECT target_type, source, confidence FROM sentence_links ORDER BY target_type"
            ).fetchall()
            self.assertEqual([r[0] for r in rows], ["figure", "table"])
            self.assertTrue(all(r[1] == "jats-regex" and r[2] == 0.6 for r in rows))
            conn.close()


class FakeClient:
    def __init__(self, results):
        self.results = results

    def search(self, query, page_size=25):
        return self.results

    def download_and_import(self, pmcid, xml_dir=None, db_path=None):
        return {"pmcid": pmcid, "status": "imported", "sections": 1, "links": 2}


class EuropePmcBatchTests(unittest.TestCase):
    def test_select_open_access(self) -> None:
        results = [
            {"pmcid": "PMC1", "isOpenAccess": "Y"},
            {"pmcid": "PMC2", "isOpenAccess": "N"},
            {"pmcid": "", "isOpenAccess": "Y"},
        ]
        self.assertEqual(europe_pmc_batch.select_open_access(results), ["PMC1"])

    def test_batch_import_counts(self) -> None:
        summary = europe_pmc_batch.batch_import(
            ["PMC1", "PMC2"], client=FakeClient([]), xml_dir="x", db_path="d"
        )
        self.assertEqual(summary["imported"], 2)
        self.assertEqual(summary["sections"], 2)

    def test_run_query_filters(self) -> None:
        client = FakeClient([{"pmcid": "PMC1", "isOpenAccess": "Y"}])
        summary = europe_pmc_batch.run_query(
            "q", max_items=1, client=client, xml_dir="x", db_path="d"
        )
        self.assertEqual(summary["candidates"], 1)
        self.assertEqual(summary["imported"], 1)


class PreprintIngestTests(unittest.TestCase):
    def test_ingest_pdf_no_parse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(
                preprint_ingest, "download_pdf", return_value=Path(tmp) / "a.pdf"
            ) as downloader:
                result = preprint_ingest.ingest_pdf(
                    "https://x/a.pdf", "a.pdf", {"title": "T"},
                    documents_dir=tmp, db_path=Path(tmp) / "t.db", parse=False,
                )
            self.assertFalse(result["parsed"])
            downloader.assert_called_once()

    def test_ingest_pdf_parse_calls_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(preprint_ingest, "download_pdf"), mock.patch(
                "build_db.parse_service.parse_and_store",
                return_value={"paper_id": "p1", "title": "T", "paragraph_count": 3},
            ) as parser, mock.patch.object(preprint_ingest, "_patch_metadata") as patcher:
                result = preprint_ingest.ingest_pdf(
                    "https://x/a.pdf", "a.pdf", {"title": "T"},
                    documents_dir=tmp, db_path=Path(tmp) / "t.db", parse=True,
                )
            self.assertTrue(result["parsed"])
            parser.assert_called_once()
            patcher.assert_called_once()


class MetadataBackfillTests(unittest.TestCase):
    def test_backfill_fills_missing_journal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT, "
                "journal TEXT, year TEXT, doi TEXT, authors TEXT, updated_at TEXT)"
            )
            conn.execute(
                "INSERT INTO papers VALUES ('p1','Some title',NULL,NULL,NULL,NULL,NULL)"
            )
            conn.commit()
            conn.close()
            with mock.patch.object(
                backfill_metadata, "crossref_work", return_value={}
            ), mock.patch.object(
                backfill_metadata,
                "crossref_search",
                return_value={"journal": "J", "year": "2026", "authors": ["A B"]},
            ):
                stats = backfill_metadata.backfill(db, limit=5, pause=0)
            self.assertEqual(stats["updated"], 1)
            conn = sqlite3.connect(db)
            self.assertEqual(
                conn.execute("SELECT journal FROM papers WHERE paper_id='p1'").fetchone()[0],
                "J",
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
