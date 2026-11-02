from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.repair_paragraph_vectors import delete_ids, load_paragraphs


class RepairParagraphVectorsTests(unittest.TestCase):
    def test_load_paragraphs_filters_short_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "r.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE paragraphs (para_id TEXT PRIMARY KEY, paper_id TEXT, "
                "section_level1 TEXT, section_level2 TEXT, text TEXT, sequence INTEGER)"
            )
            conn.execute(
                "INSERT INTO paragraphs VALUES ('p1','paper','S1','S2','This is long enough.',1)"
            )
            conn.execute("INSERT INTO paragraphs VALUES ('p2','paper','S1','S2','short',2)")
            conn.commit()
            conn.close()
            rows = load_paragraphs(db)
            self.assertEqual(set(rows), {"p1"})
            self.assertEqual(rows["p1"]["section_level1"], "S1")

    def test_delete_ids_batches(self):
        class FakeCollection:
            def __init__(self):
                self.deleted = []

            def delete(self, ids):
                self.deleted.extend(ids)

        fake = FakeCollection()
        self.assertEqual(delete_ids(fake, ["a", "b", "c", "d", "e"], 2), 5)
        self.assertEqual(fake.deleted, ["a", "b", "c", "d", "e"])


if __name__ == "__main__":
    unittest.main()
