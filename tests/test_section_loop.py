"""Tests for the section draft/review retry policy."""

from __future__ import annotations

import unittest

from services.review.section_loop import SectionAttempt, write_section_loop


class FakeWriter:
    def __init__(self, scores: list[float], notes: list[str] | None = None):
        self.scores = scores
        self.notes = notes or [f"note-{index}" for index in range(len(scores))]
        self.generated: list[str] = []
        self.reviewed: list[str] = []

    def generate(self, feedback: str) -> str:
        self.generated.append(feedback)
        return f"draft-{len(self.generated)}"

    def review(self, text: str) -> tuple[float, str]:
        index = len(self.reviewed)
        self.reviewed.append(text)
        return self.scores[index], self.notes[index]


class SectionLoopTests(unittest.TestCase):
    def test_passes_first_time(self) -> None:
        writer = FakeWriter([85.0])
        result = write_section_loop(writer.generate, writer.review)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.text, "draft-1")
        self.assertEqual(len(writer.reviewed), 1)

    def test_retries_with_feedback(self) -> None:
        writer = FakeWriter([40.0, 78.0], notes=["needs citations", "ok"])
        result = write_section_loop(writer.generate, writer.review)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.score, 78.0)
        self.assertEqual(writer.generated, ["", "needs citations"])

    def test_returns_best_attempt_when_all_fail(self) -> None:
        writer = FakeWriter([40.0, 35.0])
        result = write_section_loop(writer.generate, writer.review)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(result.score, 40.0)
        self.assertEqual(result.text, "draft-1")

    def test_single_attempt_mode(self) -> None:
        writer = FakeWriter([10.0])
        result = write_section_loop(writer.generate, writer.review, max_attempts=1)
        self.assertEqual(result.attempts, 1)
        self.assertFalse(result.passed)

    def test_threshold_is_configurable(self) -> None:
        writer = FakeWriter([70.0, 72.0])
        result = write_section_loop(writer.generate, writer.review, threshold=75.0)
        self.assertEqual(result.attempts, 2)
        self.assertFalse(result.passed)
        self.assertEqual(result.score, 72.0)

    def test_invalid_max_attempts(self) -> None:
        with self.assertRaises(ValueError):
            write_section_loop(lambda f: "x", lambda t: (1.0, ""), max_attempts=0)

    def test_generate_error_propagates(self) -> None:
        def boom(feedback: str) -> str:
            raise RuntimeError("llm down")

        with self.assertRaises(RuntimeError):
            write_section_loop(boom, lambda t: (100.0, ""))

    def test_attempt_dataclass_reports_pass(self) -> None:
        self.assertTrue(SectionAttempt("x", 60.0, "", 1).passed)
        self.assertFalse(SectionAttempt("x", 59.9, "", 1).passed)


if __name__ == "__main__":
    unittest.main()
