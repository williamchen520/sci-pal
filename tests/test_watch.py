"""Watch runner: selection, dedup, abstract ingest, digest."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_db.watch_schema import migrate
from services.watch import repo
from services.watch.runner import run_profile


def _candidate(index: int, journal: str = "J1") -> dict:
    return {
        "doi": f"10.1000/test.{index}",
        "title": f"Hepatocellular carcinoma immunotherapy study {index}",
        "abstract": "Response rate improved with checkpoint inhibitors in this cohort.",
        "journal": journal,
        "issn_l": "1234-5678",
        "published": "2026-10-20",
        "authors": ["A Author"],
    }


class WatchRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "t.db"
        conn = sqlite3.connect(self.db)
        conn.execute(
            "CREATE TABLE papers (paper_id TEXT PRIMARY KEY, filename TEXT NOT NULL, "
            "title TEXT, authors TEXT, abstract TEXT, journal TEXT, year INTEGER, doi TEXT, "
            "parse_status TEXT, parse_engine TEXT, acquisition TEXT, "
            "created_at TEXT, updated_at TEXT)"
        )
        conn.commit()
        conn.close()
        migrate(self.db)
        conn = repo.connect(self.db)
        self.profile_id = repo.create_profile(
            conn,
            {
                "name": "HCC",
                "field_text": "hepatocellular carcinoma immunotherapy",
                "keywords": "checkpoint inhibitor",
                "max_items": 2,
                "same_journal_limit": 1,
                "interval_days": 3,
                "window_days": 7,
            },
        )
        repo.set_journals(
            conn,
            self.profile_id,
            [{"issn_l": "1234-5678", "name": "J1", "source": "manual"}],
        )
        conn.close()
        self.now = datetime(2026, 10, 27, tzinfo=timezone.utc)

    def test_select_ingest_and_digest(self) -> None:
        candidates = [_candidate(1, "J1"), _candidate(2, "J2"), _candidate(3, "J3")]
        result = run_profile(
            self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: candidates, fulltext_fn=lambda *a: None
        )
        self.assertEqual(result["found"], 3)
        self.assertEqual(result["selected"], 2)
        self.assertEqual(result["imported_abstract"], 2)
        self.assertIn("文献监测", result["digest"])

        conn = sqlite3.connect(self.db)
        rows = conn.execute("SELECT DOI, acquisition FROM papers").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row[1] == "abstract" for row in rows))
        items = conn.execute("SELECT title, status FROM watch_items").fetchall()
        self.assertEqual(len(items), 2)
        conn.close()

    def test_second_run_deduplicates(self) -> None:
        candidates = [_candidate(1), _candidate(2)]
        run_profile(self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: candidates, fulltext_fn=lambda *a: None)
        result = run_profile(
            self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: candidates, fulltext_fn=lambda *a: None
        )
        self.assertEqual(result["selected"], 0)
        self.assertEqual(result["skipped"], 2)

    def test_owner_isolation(self) -> None:
        conn = repo.connect(self.db)
        alice = repo.create_profile(conn, {"name": "A", "owner": "alice"})
        bob = repo.create_profile(conn, {"name": "B", "owner": "bob"})
        self.assertEqual(
            [p["id"] for p in repo.list_profiles(conn, "alice")], [alice]
        )
        self.assertIsNone(repo.get_profile(conn, bob, "alice"))
        self.assertIsNotNone(repo.get_profile(conn, bob, "bob"))
        conn.close()

    def test_empty_run_heartbeat(self) -> None:
        first = run_profile(
            self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: []
        )
        self.assertTrue(first["heartbeat"])
        self.assertIn("无新增", first["digest"])
        second = run_profile(
            self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: []
        )
        self.assertFalse(second["heartbeat"])
        self.assertEqual(second["digest"], "")

    def test_heartbeat_after_30_days(self) -> None:
        conn = sqlite3.connect(self.db)
        old = (self.now - timedelta(days=31)).isoformat()
        conn.execute(
            "UPDATE watch_profiles SET last_push_at = ?, last_heartbeat_at = NULL WHERE id = ?",
            (old, self.profile_id),
        )
        conn.commit()
        conn.close()
        result = run_profile(
            self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: []
        )
        self.assertTrue(result["heartbeat"])

    def test_fulltext_upgrade(self) -> None:
        def fake_fulltext(db, conn, candidate, abstract_id):
            full_id = "paper_watch_pmc1"
            conn.execute(
                "INSERT OR IGNORE INTO papers (paper_id, filename, title, doi, "
                "parse_status, acquisition) VALUES (?, 'PMC1.xml', ?, ?, 'completed', 'fulltext')",
                (full_id, candidate.get("title"), candidate.get("doi")),
            )
            conn.execute("DELETE FROM papers WHERE paper_id = ?", (abstract_id,))
            conn.commit()
            return full_id

        result = run_profile(
            self.db,
            self.profile_id,
            now=self.now,
            candidate_fn=lambda *a, **k: [_candidate(1)],
            fulltext_fn=fake_fulltext,
        )
        self.assertEqual(result["imported_full"], 1)
        conn = sqlite3.connect(self.db)
        rows = conn.execute("SELECT acquisition FROM papers").fetchall()
        self.assertEqual([row[0] for row in rows], ["fulltext"])
        conn.close()

    def test_oa_pdf_fallback(self) -> None:
        def fake_oa(db, conn, candidate, abstract_id):
            full_id = "paper_watch_oa1"
            conn.execute(
                "INSERT OR IGNORE INTO papers (paper_id, filename, title, doi, "
                "parse_status, acquisition) VALUES (?, 'oa1.pdf', ?, ?, 'completed', 'fulltext')",
                (full_id, candidate.get("title"), candidate.get("doi")),
            )
            conn.execute("DELETE FROM papers WHERE paper_id = ?", (abstract_id,))
            conn.commit()
            return full_id

        result = run_profile(
            self.db,
            self.profile_id,
            now=self.now,
            candidate_fn=lambda *a, **k: [_candidate(1)],
            fulltext_fn=lambda *a: None,
            oa_pdf_fn=fake_oa,
        )
        self.assertEqual(result["imported_full"], 1)

    def test_same_journal_limit(self) -> None:
        candidates = [_candidate(1, "J1"), _candidate(2, "J1"), _candidate(3, "J2")]
        result = run_profile(
            self.db, self.profile_id, now=self.now, candidate_fn=lambda *a, **k: candidates, fulltext_fn=lambda *a: None
        )
        journals = [
            row[0]
            for row in sqlite3.connect(self.db).execute(
                "SELECT journal FROM watch_items ORDER BY id"
            )
        ]
        self.assertEqual(journals.count("J1"), 1)
        self.assertEqual(result["selected"], 2)


if __name__ == "__main__":
    unittest.main()
