from __future__ import annotations

import unittest
from unittest import mock

from services.search.ingest import IngestService


class IngestPGBatchTests(unittest.TestCase):
    def test_batch_pg_only_skips_sqlite(self):
        service = IngestService(
            db_path="unused.db",
            xml_dir=".",
            log=lambda *_: None,
        )
        parsed = [
            {
                "pmc_id": "PMC1",
                "data": {
                    "title": "T",
                    "abstract": "A",
                    "authors": "X",
                    "paragraphs": [{"text": "One. Two.", "path": ["Intro"]}],
                },
            }
        ]
        service.writer = None
        with mock.patch("services.papers.pg_writes.pg_only", return_value=True):
            with mock.patch("services.papers.pg_writes.enabled", return_value=True):
                with mock.patch(
                    "services.papers.pg_writes.write_papers_batch", return_value=True
                ) as write:
                    self.assertEqual(service._write_batch(None, parsed), 1)
        write.assert_called_once()
        paper_rows, children = write.call_args.args
        self.assertTrue(paper_rows[0]["paper_id"].startswith("paper_PMC1"))
        self.assertEqual(len(children[0][1]), 1)


if __name__ == "__main__":
    unittest.main()
