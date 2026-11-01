"""JATS placement tests for schema v2 (P2)."""

from __future__ import annotations

import unittest

from build_db.jats_parser import parse_jats

XML = """<?xml version="1.0"?>
<article xmlns:xlink="http://www.w3.org/1999/xlink">
  <front><article-meta><title-group><article-title>T</article-title></title-group></article-meta></front>
  <body>
    <sec><title>Results</title>
      <p>Text.</p>
      <fig id="F1"><label>Fig 1</label><caption>Cap.</caption></fig>
      <table-wrap id="T1"><label>Table 1</label><caption>Tcap.</caption></table-wrap>
      <sec><title>Sub</title><p>Sub text.</p></sec>
    </sec>
  </body>
</article>
"""


class JatsPlacementTests(unittest.TestCase):
    def test_figure_and_table_keep_parent_section(self) -> None:
        data = parse_jats(XML)
        self.assertEqual(len(data["sections"]), 2)
        fig = data["figures"][0]
        table = data["tables"][0]
        self.assertEqual(fig["section_id"], data["sections"][0]["section_id"])
        self.assertEqual(table["section_id"], data["sections"][0]["section_id"])
        self.assertTrue(fig["xpath"].startswith("/article/body/sec[1]"))
        self.assertEqual(data["sections"][1]["parent_id"], data["sections"][0]["section_id"])

    def test_outside_figure_stays_unresolved(self) -> None:
        data = parse_jats(XML.replace("</body>", "</body><fig id='F2'><label>F2</label></fig>"))
        fig = [item for item in data["figures"] if item["id"] == "F2"][0]
        self.assertIsNone(fig["section_id"])


if __name__ == "__main__":
    unittest.main()
