"""Semantic grounding tests (model-free helpers)."""

from __future__ import annotations

import unittest

from services.qa.semantic_grounding import split_claims


class SemanticGroundingTests(unittest.TestCase):
    def test_split(self) -> None:
        claims = split_claims(
            "The response rate was 42% in this cohort and was well tolerated [P1]. "
            "Another sentence without enough evidence [P2]."
        )
        self.assertEqual(len(claims), 2)


if __name__ == "__main__":
    unittest.main()
