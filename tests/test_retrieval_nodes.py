"""RetrievalNode tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.search.retrieval_nodes import RetrievalNode, paragraph_nodes


class RetrievalNodeTests(unittest.TestCase):
    def test_node_candidate(self) -> None:
        node = RetrievalNode(
            node_id="p1", level="paragraph", text="hello", paper_id="paper",
            section_id="sec", metadata={"section_l1": "Intro"},
        )
        candidate = node.as_candidate()
        self.assertEqual(candidate["para_id"], "p1")
        self.assertEqual(candidate["section_id"], "sec")
        self.assertEqual(candidate["node_level"], "paragraph")

    def test_paragraph_nodes(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE paragraphs (para_id TEXT, paper_id TEXT, section_id TEXT, "
                "text TEXT, section_level1 TEXT, section_level2 TEXT)"
            )
            conn.execute("INSERT INTO paragraphs VALUES ('p1','paper','sec','body','Intro','')")
            conn.commit()
            conn.close()
            nodes = paragraph_nodes(db, ["sec"])
            self.assertEqual(len(nodes), 1)
            self.assertEqual(nodes[0].text, "body")


if __name__ == "__main__":
    unittest.main()
