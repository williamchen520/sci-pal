"""Sentence trace API (JSON + image 404 path)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.papers_actions import build_papers_actions_blueprint


class TraceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / "documents").mkdir()
        self.db = root / "research.db"
        conn = sqlite3.connect(self.db)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT, filename TEXT, title TEXT);
            CREATE TABLE sections (section_id TEXT PRIMARY KEY, paper_id TEXT,
                parent_id TEXT, level INTEGER, title TEXT, seq INTEGER);
            CREATE TABLE sentences (sentence_id TEXT PRIMARY KEY, para_id TEXT,
                paper_id TEXT, text TEXT, sequence INTEGER, page INTEGER, bbox TEXT,
                section_id TEXT);
            CREATE TABLE sentence_links (link_id TEXT PRIMARY KEY, sentence_id TEXT,
                para_id TEXT, paper_id TEXT, source_type TEXT, target_type TEXT,
                target_id TEXT, relation TEXT, page INTEGER, bbox TEXT,
                source TEXT, confidence REAL);
            CREATE TABLE citations (citation_id TEXT PRIMARY KEY, raw_text TEXT,
                doi TEXT, title TEXT);
            CREATE TABLE figures (fig_id TEXT PRIMARY KEY, fig_number TEXT,
                caption TEXT, page INTEGER, bbox TEXT);
            CREATE TABLE tables (table_id TEXT PRIMARY KEY, table_number TEXT, caption TEXT);
            """
        )
        conn.execute("INSERT INTO papers VALUES ('p1','a.pdf','T')")
        conn.execute("INSERT INTO sections VALUES ('s1','p1',NULL,1,'Intro',1)")
        conn.execute(
            "INSERT INTO sentences VALUES ('sent1','para1','p1','See Fig. 1.',1,2,"
            "'10,20,100,40','s1')"
        )
        conn.execute(
            "INSERT INTO sentence_links VALUES ('l1','sent1','para1','p1','sentence',"
            "'figure','f1','mentions',2,'10,20,100,40','regex',0.6)"
        )
        conn.execute("INSERT INTO figures VALUES ('f1','Fig 1','Cap',2,'10,20,100,40')")
        conn.commit()
        conn.close()

        app = Flask(__name__)
        app.register_blueprint(
            build_papers_actions_blueprint(
                db_path=self.db,
                project_root=root,
                get_task_manager=lambda: None,
                log=app.logger,
            )
        )
        self.client = app.test_client()

    def test_trace_json(self) -> None:
        response = self.client.get("/api/papers/p1/trace?sentence_id=sent1")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["page"], 2)
        self.assertEqual(body["bbox"], "10,20,100,40")
        self.assertEqual(body["section_path"], ["Intro"])
        self.assertEqual(len(body["links"]), 1)
        self.assertEqual(body["links"][0]["detail"]["fig_number"], "Fig 1")

    def test_trace_requires_sentence_id(self) -> None:
        self.assertEqual(self.client.get("/api/papers/p1/trace").status_code, 400)

    def test_trace_unknown_sentence(self) -> None:
        self.assertEqual(
            self.client.get("/api/papers/p1/trace?sentence_id=nope").status_code, 404
        )

    def test_trace_png_without_pdf(self) -> None:
        self.assertEqual(
            self.client.get("/api/papers/p1/trace.png?sentence_id=sent1").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
