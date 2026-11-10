"""Logical sentence-window policy tests."""

from __future__ import annotations

import unittest

from services.search.sentence_window import WindowPolicy, build_context


def row(sid: str, text: str, seq: int, section_id: str = "s1", **extra):
    return {"sentence_id": sid, "para_id": "p1", "paper_id": "paper", "text": text, "sequence": seq, "section_id": section_id, **extra}


def anchor(text: str = "The response rate was 42%.") -> dict:
    return {"sentence_id": "s3", "para_id": "p1", "paper_id": "paper", "text": text}


class LogicalWindowTests(unittest.TestCase):
    def policy(self, **kwargs) -> WindowPolicy:
        return WindowPolicy(max_chars=1200, max_scan=6, relevance_threshold=0.5, logic_terms=["however", "therefore"], heading_terms=["results", "methods"], **kwargs)

    def test_logic_word_is_pulled_in_despite_low_relevance(self) -> None:
        rows = [
            row("s1", "Unrelated background text about mice.", 1),
            row("s2", "However, the effect reversed in the second cohort.", 2),
            row("s3", "The response rate was 42%.", 3),
        ]
        unit = build_context(anchor(), rows, query="response rate cohort", policy=self.policy())
        self.assertEqual(unit.mode, "logical_window")
        self.assertIn("s2", [item["sentence_id"] for item in unit.sentences])
        self.assertEqual(next(item for item in unit.sentences if item["sentence_id"] == "s2")["reason"], "logic")

    def test_low_relevance_without_logic_is_skipped(self) -> None:
        rows = [
            row("s1", "Unrelated background text about mice.", 1),
            row("s3", "The response rate was 42%.", 3),
        ]
        unit = build_context(anchor(), rows, query="response rate", policy=self.policy())
        self.assertNotIn("s1", [item["sentence_id"] for item in unit.sentences])

    def test_heading_stops_scan(self) -> None:
        rows = [
            row("s3", "The response rate was 42%.", 3),
            row("s4", "Results", 4),
            row("s5", "However, the next section has a different claim.", 5),
        ]
        unit = build_context(anchor(), rows, query="response rate", policy=self.policy())
        ids = [item["sentence_id"] for item in unit.sentences]
        self.assertNotIn("s4", ids)
        self.assertNotIn("s5", ids)

    def test_section_change_stops_scan(self) -> None:
        rows = [
            row("s4", "However, this belongs to another section.", 4, section_id="s2"),
            row("s3", "The response rate was 42%.", 3),
        ]
        unit = build_context(anchor(), rows, query="response rate", policy=self.policy())
        self.assertNotIn("s4", [item["sentence_id"] for item in unit.sentences])

    def test_blank_line_stops_scan(self) -> None:
        rows = [
            row("s3", "The response rate was 42%.", 3),
            row("s4", "However, this follows a blank line.", 4, blank_before=True),
        ]
        unit = build_context(anchor(), rows, query="response rate", policy=self.policy())
        self.assertNotIn("s4", [item["sentence_id"] for item in unit.sentences])

    def test_hard_char_cap(self) -> None:
        rows = [row("s3", "The response rate was 42%.", 3)]
        for index in range(4, 14):
            rows.append(row(f"s{index}", "However, " + ("long context sentence " * 40), index))
        unit = build_context(anchor(), rows, query="response rate", policy=self.policy())
        self.assertLessEqual(len(unit.text), 1200)

    def test_logic_terms_are_configurable(self) -> None:
        policy = WindowPolicy(max_chars=1200, max_scan=6, relevance_threshold=0.9, logic_terms=["然而"], heading_terms=[])
        rows = [
            row("s2", "然而，这个效应在第二组中反转。", 2),
            row("s3", "缓解率为 42%。", 3),
        ]
        unit = build_context(anchor("缓解率为 42%。"), rows, query="无关问题", policy=policy)
        self.assertIn("s2", [item["sentence_id"] for item in unit.sentences])


if __name__ == "__main__":
    unittest.main()
