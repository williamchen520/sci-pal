from __future__ import annotations

import os
import unittest
from unittest import mock

from build_db import build_sections_tree as tree


class SectionPGOnlyTests(unittest.TestCase):
    def test_pg_only_uses_pg_rows(self):
        rows = [
            {
                "para_id": "p1",
                "section_path": '["Introduction"]',
                "section_level1": "Introduction",
                "section_level2": None,
                "section_level3": None,
                "page": 1,
                "bbox": None,
            }
        ]
        with mock.patch.dict(
            os.environ,
            {
                "SCIPAL_INGEST_PG_ONLY": "1",
                "SCIPAL_PAPER_WRITE_BACKEND": "postgres",
                "SCIPAL_PG_DSN": "postgresql://x",
            },
        ):
            with mock.patch.object(tree.pg_writes, "enabled", return_value=True):
                with mock.patch.object(
                    tree, "_pg_paragraph_rows", return_value=rows
                ):
                    with mock.patch.object(
                        tree.pg_writes, "replace_sections", return_value=True
                    ) as replace:
                        stats = tree.build_for_paper("unused.db", "paper1")
        self.assertEqual(stats["paragraphs"], 1)
        self.assertEqual(stats["sections"], 1)
        replace.assert_called_once()


if __name__ == "__main__":
    unittest.main()
