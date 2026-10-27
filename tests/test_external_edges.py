"""Cursor search, batch skip logic, external citation edges."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from build_db import build_external_edges
from services.search import europe_pmc


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class CursorSearchTests(unittest.TestCase):
    def test_search_all_paginates(self) -> None:
        page1 = {"resultList": {"result": [{"pmcid": "PMC1"}]}, "nextCursorMark": "A"}
        page2 = {"resultList": {"result": [{"pmcid": "PMC2"}]}, "nextCursorMark": "A"}
        responses = [FakeResponse(page1), FakeResponse(page2)]
        with mock.patch.object(europe_pmc.requests, "get", side_effect=responses):
            rows = europe_pmc.EuropePMCClient().search_all("q", max_items=10)
        self.assertEqual([r["pmcid"] for r in rows], ["PMC1", "PMC2"])


class ExternalEdgeTests(unittest.TestCase):
    def _db(self, path: Path) -> None:
        conn = sqlite3.connect(path)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, doi TEXT);
            CREATE TABLE paper_links (
                link_id TEXT PRIMARY KEY, source_paper_id TEXT, target_paper_id TEXT,
                target_doi TEXT, relation TEXT, evidence_sentence_id TEXT,
                source TEXT, confidence REAL
            );
            """
        )
        conn.execute("INSERT INTO papers VALUES ('p1','10.1/a')")
        conn.execute("INSERT INTO papers VALUES ('p2','10.1/b')")
        conn.commit()
        conn.close()

    def test_build_from_crossref_and_openalex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            self._db(db)
            with mock.patch.object(
                build_external_edges,
                "crossref_work",
                return_value={"references": [{"doi": "10.1/b"}, {"doi": "10.9/x"}]},
            ), mock.patch.object(
                build_external_edges,
                "openalex_work",
                return_value={"referenced_works": ["W1"]},
            ), mock.patch.object(
                build_external_edges,
                "openalex_resolve_ids",
                return_value={"W1": "10.1/b"},
            ):
                stats = build_external_edges.build(db, limit=1, pause=0)
            self.assertEqual(stats["crossref_edges"], 2)
            self.assertEqual(stats["openalex_edges"], 1)
            conn = sqlite3.connect(db)
            rows = conn.execute(
                "SELECT source, confidence, target_paper_id, target_doi "
                "FROM paper_links ORDER BY source"
            ).fetchall()
            conn.close()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "crossref_refs")
            self.assertEqual(rows[0][3], "10.9/x")
            local_row = [r for r in rows if r[3] == "10.1/b"][0]
            self.assertEqual(local_row[2], "p2")  # resolved to local paper
            self.assertEqual(local_row[0], "openalex_refs")  # higher confidence wins

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            self._db(db)
            with mock.patch.object(
                build_external_edges,
                "crossref_work",
                return_value={"references": [{"doi": "10.9/x"}]},
            ), mock.patch.object(
                build_external_edges, "openalex_work", return_value={}
            ), mock.patch.object(
                build_external_edges, "openalex_resolve_ids", return_value={}
            ):
                build_external_edges.build(db, limit=1, dry_run=True, pause=0)
            conn = sqlite3.connect(db)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM paper_links").fetchone()[0], 0
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
