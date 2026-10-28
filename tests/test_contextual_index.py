"""Contextual paragraph text tests."""

from __future__ import annotations

import unittest

from build_db.build_contextual_paragraph_index import contextual_text


class ContextualTextTests(unittest.TestCase):
    def test_prefix(self) -> None:
        text = contextual_text("Paper", "Intro > Methods", "Body.")
        self.assertEqual(text, "Paper > Intro > Methods. Body.")

    def test_empty(self) -> None:
        self.assertEqual(contextual_text("", "", "Body."), "Body.")


if __name__ == "__main__":
    unittest.main()
