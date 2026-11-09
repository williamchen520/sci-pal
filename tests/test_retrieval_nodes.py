"""RetrievalNode tests."""

from __future__ import annotations

import unittest
from unittest import mock

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
        class Cursor:
            def fetchall(self):
                return [{"para_id": "p1", "paper_id": "paper", "section_id": "sec",
                         "text": "body", "section_level1": "Intro", "section_level2": ""}]

        class FakePG:
            def execute(self, sql, params=None):
                return Cursor()

            def close(self):
                pass

        with mock.patch("services.db.pg_pool.pg_connection", return_value=FakePG()):
            nodes = paragraph_nodes("unused.db", ["sec"])
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].text, "body")


if __name__ == "__main__":
    unittest.main()
