"""GROBID endpoint switching (CRF vs full) and parse-service wiring."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from build_db.parse_service import ParseCancelled, parse_running_count
from build_db.parsers.pipeline import resolve_grobid_url


class GrobidSwitchTests(unittest.TestCase):
    def test_default_crf_url(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(resolve_grobid_url("auto"), "http://127.0.0.1:8070")
            self.assertEqual(resolve_grobid_url("crf"), "http://127.0.0.1:8070")

    def test_full_falls_back_when_unset(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_GROBID_URL": "http://g:8070"}, clear=True):
            self.assertEqual(resolve_grobid_url("full"), "http://g:8070")

    def test_full_uses_dedicated_url(self) -> None:
        env = {
            "SCIPAL_GROBID_URL": "http://g-crf:8070",
            "SCIPAL_GROBID_URL_FULL": "http://g-full:8071",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(resolve_grobid_url("full"), "http://g-full:8071")
            self.assertEqual(resolve_grobid_url("auto"), "http://g-crf:8070")

    def test_legacy_grobid_url_env(self) -> None:
        with mock.patch.dict(os.environ, {"GROBID_URL": "http://legacy:8070"}, clear=True):
            self.assertEqual(resolve_grobid_url("crf"), "http://legacy:8070")


class ParseServiceTests(unittest.TestCase):
    def test_cancelled_carries_stage(self) -> None:
        exc = ParseCancelled("cancelled", stage="排队期间")
        self.assertEqual(exc.stage, "排队期间")

    def test_running_count_returns_zero_for_empty_db(self) -> None:
        import sqlite3
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE tasks (id TEXT, type TEXT, status TEXT)")
            conn.commit()
            conn.close()
            self.assertEqual(parse_running_count(db), 0)


if __name__ == "__main__":
    unittest.main()
