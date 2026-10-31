"""Retry utility / parser fallback tests."""

from __future__ import annotations

import unittest

from services.utils.retry_utils import ParserFallbackChain, ParserFallbackError


class _FailOnce:
    def parse(self, value):
        raise RuntimeError("boom")


class _Pass:
    def parse(self, value):
        return f"ok:{value}"


class _AlwaysFail:
    def parse(self, value):
        raise ValueError("nope")


class ParserFallbackChainTests(unittest.TestCase):
    def test_falls_back_to_next_parser(self) -> None:
        chain = ParserFallbackChain([("first", _FailOnce()), ("second", _Pass())])
        self.assertEqual(chain.parse("x"), "ok:x")
        stats = chain.get_stats()
        self.assertEqual(stats["total_attempts"], 2)
        self.assertEqual(stats["total_successes"], 1)
        self.assertEqual(stats["total_failures"], 1)

    def test_all_parsers_failed_raises(self) -> None:
        chain = ParserFallbackChain()
        chain.add_parser("a", _AlwaysFail()).add_parser("b", _AlwaysFail())
        with self.assertRaises(ParserFallbackError):
            chain.parse("x")
        self.assertEqual(chain.get_stats()["total_failures"], 2)

    def test_empty_chain_raises(self) -> None:
        with self.assertRaises(ParserFallbackError):
            ParserFallbackChain().parse("x")


if __name__ == "__main__":
    unittest.main()
