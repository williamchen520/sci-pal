"""Signed URL + PDF Range tests."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from flask import Flask

from routes.papers_actions import build_papers_actions_blueprint
from services.security.signed_url import sign_path, verify_path


class SignedUrlTests(unittest.TestCase):
    def test_sign_and_verify(self) -> None:
        url = sign_path("/api/papers/p1/pdf", 60)
        path, _, query = url.partition("?")
        params = dict(part.split("=") for part in query.split("&"))
        self.assertTrue(verify_path(path, params["token"], params["expires"]))

    def test_tampered_token(self) -> None:
        url = sign_path("/api/papers/p1/pdf", 60)
        self.assertFalse(verify_path("/api/papers/p2/pdf", url.split("token=")[1].split("&")[0], url.split("expires=")[1]))

    def test_expired(self) -> None:
        url = sign_path("/api/papers/p1/pdf", -1)
        path, _, query = url.partition("?")
        params = dict(part.split("=") for part in query.split("&"))
        self.assertFalse(verify_path(path, params["token"], params["expires"]))


class PdfServeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        docs = root / "documents"
        docs.mkdir()
        (docs / "a.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 2000)
        self.db = root / "t.db"
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE papers (paper_id TEXT, filename TEXT, title TEXT)")
        conn.execute("INSERT INTO papers VALUES ('p1','a.pdf','T')")
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

    def tearDown(self) -> None:
        os.environ.pop("SCIPAL_REQUIRE_SIGNED_PDF", None)

    def test_requires_signed_url(self) -> None:
        os.environ["SCIPAL_REQUIRE_SIGNED_PDF"] = "1"
        self.assertEqual(self.client.get("/api/papers/p1/pdf").status_code, 403)

    def test_signed_url_and_range(self) -> None:
        os.environ["SCIPAL_REQUIRE_SIGNED_PDF"] = "1"
        signed = sign_path("/api/papers/p1/pdf", 60)
        response = self.client.get(signed, headers={"Range": "bytes=0-3"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b"%PDF")
        self.assertIn("bytes 0-3/", response.headers.get("Content-Range", ""))


if __name__ == "__main__":
    unittest.main()
