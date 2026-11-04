from __future__ import annotations

import unittest

from services.papers import pg_links


class PaperLinksUnitTests(unittest.TestCase):
    def test_link_id_stable(self):
        self.assertEqual(
            pg_links._link_id("plink", "a", "b", "cites"),
            pg_links._link_id("plink", "a", "b", "cites"),
        )
        self.assertNotEqual(
            pg_links._link_id("plink", "a", "b", "cites"),
            pg_links._link_id("plink", "a", "c", "cites"),
        )

    def test_normalize_title(self):
        self.assertEqual(pg_links._normalize_title("A  Title!"), "a title")


if __name__ == "__main__":
    unittest.main()
