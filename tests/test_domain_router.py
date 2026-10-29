"""Domain taxonomy / router tests."""

from __future__ import annotations

import unittest

from services.search.domain_taxonomy import classify_text
from services.search.domain_router import DomainRouter


class DomainTests(unittest.TestCase):
    def test_classify_hcc(self) -> None:
        domain, confidence, distribution = classify_text(
            "HCC immunotherapy after PD-1 rechallenge"
        )
        self.assertEqual(domain, "hcc_io")
        self.assertGreater(confidence, 0.0)
        self.assertIn("hcc_io", distribution)

    def test_classify_general(self) -> None:
        domain, _, _ = classify_text("A study of something unusual")
        self.assertEqual(domain, "general")

    def test_query_distribution(self) -> None:
        distribution = DomainRouter().query_distribution(
            "What is ICI rechallenge in HCC?"
        )
        self.assertGreater(distribution.get("hcc_io", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
