"""PRISMA SVG renderer tests."""

from __future__ import annotations

import unittest

from services.review.prisma_svg import render


class PrismaSvgTests(unittest.TestCase):
    def test_render_counts(self) -> None:
        svg = render("HCC <review>", {"identified": 10, "screened": 8, "included": 3, "excluded": 5, "pending": 2})
        self.assertIn("Records identified: 10", svg)
        self.assertIn("Studies included: 3", svg)
        self.assertIn("&lt;review&gt;", svg)
        self.assertTrue(svg.startswith("<svg"))

    def test_empty(self) -> None:
        svg = render("Empty", {})
        self.assertIn("Records identified: 0", svg)


if __name__ == "__main__":
    unittest.main()
