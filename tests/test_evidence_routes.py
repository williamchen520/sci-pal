"""Evidence context + verify HTTP routes."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.evidence import build_evidence_blueprint


class EvidenceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.db = root / "research.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT, title TEXT, journal TEXT, year INTEGER, doi TEXT);
            CREATE TABLE sections (section_id TEXT PRIMARY KEY, paper_id TEXT, parent_id TEXT,
                level INTEGER, title TEXT, seq INTEGER, path TEXT, depth INTEGER);
            CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT, section_id TEXT,
                text TEXT, sequence INTEGER, page INTEGER,
                section_level1 TEXT, section_level2 TEXT, section_level3 TEXT);
            CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, para_id TEXT, paper_id TEXT,
                text TEXT, sequence INTEGER, page INTEGER, bbox TEXT, section_id TEXT,
                char_start INTEGER, char_end INTEGER);
            """
        )
        conn.execute("INSERT INTO papers VALUES ('p1','Title','J',2026,'10.1/x')")
        conn.execute("INSERT INTO sections VALUES ('s1','p1',NULL,1,'Results',1,'1',1)")
        conn.execute("INSERT INTO sections VALUES ('s2','p1','s1',2,'Efficacy',2,'1.1',2)")
        conn.execute(
            "INSERT INTO paragraphs (para_id, paper_id, section_id, text, sequence, page) "
            "VALUES ('para1','p1','s2','First para.',1,3)"
        )
        conn.execute(
            "INSERT INTO paragraphs (para_id, paper_id, section_id, text, sequence, page) "
            "VALUES ('para2','p1','s2','Second para.',2,3)"
        )
        conn.execute(
            "INSERT INTO sentences (sentence_id, para_id, paper_id, text, sequence, "
            "page, bbox, section_id) VALUES "
            "('sent1','para2','p1','Response rate was 42%.',1,3,'10,20,100,40','s2')"
        )
        conn.commit()
        conn.close()

        app = Flask(__name__)
        app.register_blueprint(
            build_evidence_blueprint(
                db_path=self.db,
                get_retriever=lambda: None,
                log=app.logger,
            )
        )
        self.client = app.test_client()

    def test_context_by_sentence(self) -> None:
        response = self.client.get(
            "/api/evidence/context?paper_id=p1&sentence_id=sent1&before=1&after=1"
        )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["section_path"], ["Results", "Efficacy"])
        self.assertEqual(body["sentence"]["bbox"], "10,20,100,40")
        self.assertIn("►", body["text"])

    def test_context_unknown_sentence(self) -> None:
        response = self.client.get(
            "/api/evidence/context?paper_id=p1&sentence_id=nope"
        )
        self.assertEqual(response.status_code, 404)

    def test_verify_route(self) -> None:
        response = self.client.post(
            "/api/verify",
            json={"answer": "Claim [P1].", "evidence_ids": ["P1"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_verify_flags_missing(self) -> None:
        response = self.client.post(
            "/api/verify",
            json={"answer": "Claim [P9].", "evidence_ids": ["P1"]},
        )
        self.assertFalse(response.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
