"""Unit tests for SciFact Phase C chunk construction."""

from __future__ import annotations

import unittest

from eval.scifact_units import Sentence, boundary_chunks, hard_chunks


def _sentences() -> list[Sentence]:
    rows = [
        ("p1_s0", "one two three four five"),
        ("p1_s1", "six seven eight nine ten"),
        ("p1_s2", "eleven twelve thirteen fourteen fifteen"),
    ]
    result = []
    cursor = 0
    for index, (sentence_id, text) in enumerate(rows):
        result.append(Sentence(sentence_id, "p1", index, text, cursor, cursor + len(text)))
        cursor += len(text) + 1
    return result


class PhaseCChunkTests(unittest.TestCase):
    def test_hard_chunks_have_anchors(self) -> None:
        units = hard_chunks(_sentences(), words=5)
        self.assertEqual(len(units), 3)
        self.assertTrue(all(unit.anchors for unit in units))
        self.assertTrue(all(not unit.context for unit in units))

    def test_boundary_chunks_do_not_cut_sentences(self) -> None:
        units = boundary_chunks(_sentences(), words=10)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0].anchors, ("p1_s0", "p1_s1"))
        self.assertEqual(units[1].anchors, ("p1_s2",))
        self.assertIn("one two three", units[0].text)
        self.assertIn("eleven twelve", units[1].text)

    def test_boundary_context_is_separate(self) -> None:
        units = boundary_chunks(_sentences(), words=5)
        self.assertEqual(units[0].anchors, ("p1_s0",))
        self.assertIn("p1_s1", units[0].context)
        self.assertNotIn("p1_s1", units[0].anchors)


if __name__ == "__main__":
    unittest.main()
