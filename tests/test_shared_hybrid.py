"""Shared HybridSearch singleton tests."""

from __future__ import annotations

import unittest

from services.search import shared


class SharedHybridTests(unittest.TestCase):
    def setUp(self) -> None:
        shared.reset_shared_hybrid()
        self.addCleanup(shared.reset_shared_hybrid)

    def test_singleton_is_cached(self) -> None:
        calls = []

        def factory(**kwargs):
            calls.append(kwargs)
            return object()

        first = shared.get_shared_hybrid(factory=factory)
        second = shared.get_shared_hybrid(factory=factory)
        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)

    def test_reset_forces_new_instance(self) -> None:
        first = shared.get_shared_hybrid(factory=lambda **_: object())
        shared.reset_shared_hybrid()
        second = shared.get_shared_hybrid(factory=lambda **_: object())
        self.assertIsNot(first, second)


if __name__ == "__main__":
    unittest.main()
