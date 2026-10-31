"""P2 read-only ETL tests (no PostgreSQL server)."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.db import (
    ETLError,
    InMemoryWriter,
    PostgresCopyWriter,
    assert_snapshot,
    dry_run,
    run_etl,
)


class ETLCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "snapshot.db"
        conn = sqlite3.connect(self.source)
        conn.executescript(
            """
            CREATE TABLE papers (paper_id TEXT PRIMARY KEY, title TEXT);
            CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT, text TEXT);
            CREATE TABLE paragraphs_fts (para_id TEXT, text TEXT);
            INSERT INTO papers VALUES ('p1', 'Paper One');
            INSERT INTO paragraphs VALUES ('para1', 'p1', 'body');
            INSERT INTO paragraphs_fts VALUES ('para1', 'body');
            """
        )
        conn.commit()
        conn.close()

    def test_dry_run_counts_and_skips_fts(self) -> None:
        report = dry_run(self.source, checksum=True)
        names = [item.table for item in report.tables]
        self.assertEqual(names, ["papers", "paragraphs"])
        self.assertEqual(report.tables[0].rows, 1)
        self.assertIsNotNone(report.tables[0].checksum)

    def test_in_memory_writer_receives_rows(self) -> None:
        writer = InMemoryWriter()
        report = run_etl(self.source, writer, tables=["papers"])
        self.assertEqual(report.tables[0].rows, 1)
        self.assertEqual(writer.tables["papers"][0][0], "p1")

    def test_unknown_table_is_rejected(self) -> None:
        with self.assertRaises(ETLError):
            dry_run(self.source, tables=["nope"])

    def test_live_db_is_rejected(self) -> None:
        with self.assertRaises(ETLError):
            from services.db import LIVE_DB

            assert_snapshot(LIVE_DB)

    def test_postgres_writer_requires_driver(self) -> None:
        writer = PostgresCopyWriter("postgresql://example")
        with patch.dict(sys.modules, {"psycopg": None}):
            with self.assertRaises(ETLError):
                writer.copy_table("papers", ["paper_id"], [("p1",)])


if __name__ == "__main__":
    unittest.main()
