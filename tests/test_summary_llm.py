"""LLM summary generation tests (no real model)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from build_db import build_llm_summaries
from build_db.build_summaries import SCHEMA
from services.search.summary_llm import summarize


class SummaryLlmTests(unittest.TestCase):
    def test_summarize_valid(self) -> None:
        result = summarize("Efficacy", "The ORR was 42% in 120 patients.", llm=lambda text: "ORR was 42% in 120 patients.")
        self.assertIn("42%", result)

    def test_summarize_invalid(self) -> None:
        self.assertEqual(summarize("X", "Y", llm=lambda text: "short"), "")

    def test_build_updates_source(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        conn = sqlite3.connect(db)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO summaries (summary_id, paper_id, section_id, level, title, text, token_count) "
            "VALUES ('s1','p1','sec1',1,'Efficacy','The response rate was 42% in the trial.',8)"
        )
        conn.commit()
        conn.close()

        with mock.patch.object(
            build_llm_summaries,
            "summarize",
            return_value="The trial reported a 42% response rate in treated patients.",
        ):
            stats = build_llm_summaries.build(db, limit=10)

        conn = sqlite3.connect(db)
        source = conn.execute("SELECT summary_source FROM summaries WHERE summary_id='s1'").fetchone()[0]
        fts = conn.execute("SELECT text FROM summaries_fts WHERE summary_id='s1'").fetchone()[0]
        conn.close()
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(source, "llm")
        self.assertIn("42%", fts)


if __name__ == "__main__":
    unittest.main()
