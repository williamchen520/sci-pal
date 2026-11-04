from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from build_db.db_writer import DatabaseWriter


class IngestPGOnlyTests(unittest.TestCase):
    def test_pg_only_skips_sqlite(self):
        writer = DatabaseWriter.__new__(DatabaseWriter)
        writer.db_path = "unused.db"
        with patch.dict(
            os.environ,
            {
                "SCIPAL_INGEST_PG_ONLY": "1",
                "SCIPAL_PAPER_WRITE_BACKEND": "postgres",
            },
        ):
            with patch("services.papers.pg_writes.enabled", return_value=True):
                with patch(
                    "services.papers.pg_writes.write_parsed_paper", return_value=True
                ) as write:
                    self.assertTrue(writer.insert_paper({"paper_id": "p1"}))
        write.assert_called_once()

    def test_pg_failure_is_fail_closed(self):
        writer = DatabaseWriter.__new__(DatabaseWriter)
        writer.db_path = "unused.db"
        with patch.dict(os.environ, {"SCIPAL_INGEST_PG_ONLY": "1"}):
            with patch("services.papers.pg_writes.enabled", return_value=True):
                with patch(
                    "services.papers.pg_writes.write_parsed_paper", return_value=False
                ):
                    with self.assertRaises(Exception):
                        writer.insert_paper({"paper_id": "p1"})


if __name__ == "__main__":
    unittest.main()
