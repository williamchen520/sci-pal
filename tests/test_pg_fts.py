from __future__ import annotations

import unittest

from services.search.pg_fts import PGParagraphFTS, PGSummaryFTS


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""
        self.params = None

    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return self.rows


class StatsCursor:
    def execute(self, sql, params):
        self.sql = sql
        self.params = params
        if "unnest" in sql:
            self.rows = [
                {"term": "common", "lexeme": "common"},
                {"term": "rare", "lexeme": "rare"},
            ]
        elif "fts_term_stats" in sql:
            self.rows = [
                {"word": "common", "nentry": 1000},
                {"word": "rare", "nentry": 2},
            ]
        else:
            self.rows = []
        return self

    def fetchall(self):
        return self.rows


class PGParagraphFTSTests(unittest.TestCase):
    def test_returns_hits_and_builds_or_query(self):
        fake = FakeCursor(
            [
                {
                    "para_id": "p1",
                    "paper_id": "paper1",
                    "section_level1": "Intro",
                    "section_level2": None,
                    "text": "HCC text",
                    "rank": 0.5,
                }
            ]
        )
        hits = PGParagraphFTS(connector=lambda: fake).search(
            "ICI rechallenge in hepatocellular carcinoma", top_k=5
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].para_id, "p1")
        self.assertIn("to_tsquery", fake.sql)
        self.assertIn("|", fake.params[0])
        self.assertEqual(fake.params[-1], 5)

    def test_filters_paper_and_section(self):
        fake = FakeCursor([])
        PGParagraphFTS(connector=lambda: fake).search(
            "tumor microenvironment", paper_id="paper1", section_level1="Results"
        )
        self.assertIn("p.paper_id = %s", fake.sql)
        self.assertIn("p.section_level1 = %s", fake.sql)

    def test_empty_query(self):
        self.assertEqual(PGParagraphFTS(connector=lambda: object()).search("  "), [])

    def test_rare_term_selection(self):
        cursor = StatsCursor()
        query = PGParagraphFTS(connector=lambda: cursor)._query(
            "common rare", "any", 1, pg=cursor, source="paragraphs"
        )
        self.assertEqual(query, "rare")

    def test_recall_has_no_rank_order(self):
        fake = FakeCursor([])
        PGParagraphFTS(connector=lambda: fake).recall("tumor microenvironment", top_n=50)
        self.assertIn("LIMIT %s", fake.sql)
        self.assertNotIn("ORDER BY", fake.sql)
        self.assertEqual(fake.params[-1], 50)


class PGSummaryFTSTests(unittest.TestCase):
    def test_summary_hit(self):
        fake = FakeCursor(
            [
                {
                    "summary_id": "s1",
                    "paper_id": "paper1",
                    "section_id": "sec1",
                    "level": 1,
                    "title": "Intro",
                    "text": "Summary",
                    "rank": 0.3,
                }
            ]
        )
        hits = PGSummaryFTS(connector=lambda: fake).search("hepatocellular carcinoma", top_k=3)
        self.assertEqual(hits[0].summary_id, "s1")
        self.assertIn("FROM summaries", fake.sql)


if __name__ == "__main__":
    unittest.main()
