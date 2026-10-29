"""LLM grounding parser tests."""

from __future__ import annotations

import unittest

from services.qa.llm_grounding import build_prompt, parse_verdicts


class LLMGroundingTests(unittest.TestCase):
    def test_parse(self) -> None:
        verdicts = parse_verdicts('[{"claim": 1, "supported": true}, {"claim": 2, "supported": false}]')
        self.assertEqual(verdicts, {1: True, 2: False})

    def test_prompt(self) -> None:
        prompt = build_prompt(["claim one"], ["evidence text " * 10])
        self.assertIn("claim one", prompt)
        self.assertIn("[E1]", prompt)


if __name__ == "__main__":
    unittest.main()
