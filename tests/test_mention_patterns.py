"""Figure/table mention pattern tests."""

from __future__ import annotations

import unittest

from build_db.mention_patterns import (
    caption_number,
    figure_mentions,
    table_mentions,
)


class MentionPatternTests(unittest.TestCase):
    def test_basic_figure(self) -> None:
        self.assertEqual([n for n, _ in figure_mentions("shown in Fig. 3.")], ["3"])
        self.assertEqual([n for n, _ in figure_mentions("(Figure 2)")], ["2"])
        self.assertEqual([n for n, _ in figure_mentions("Figure 3A")], ["3A"])

    def test_multi_and_range(self) -> None:
        self.assertEqual(
            [n for n, _ in figure_mentions("(Figs. 2, 3)")], ["2", "3"]
        )
        self.assertEqual(
            [n for n, _ in figure_mentions("Figs. 2 and 3 show")], ["2", "3"]
        )
        self.assertEqual(
            [n for n, _ in figure_mentions("Figs. 2-4 show")], ["2", "3", "4"]
        )

    def test_supplementary_excluded(self) -> None:
        self.assertEqual(figure_mentions("online supplementary Figure 3"), [])
        self.assertEqual(figure_mentions("Extended Data Fig. 2"), [])
        self.assertEqual(figure_mentions("Supplementary Table 1"), [])
        self.assertEqual(
            [n for n, _ in figure_mentions("main Fig. 3")], ["3"]
        )

    def test_tables_and_chinese(self) -> None:
        self.assertEqual([n for n, _ in table_mentions("Table 2 lists")], ["2"])
        self.assertEqual([n for n, _ in table_mentions("Tables 1 and 2")], ["1", "2"])
        self.assertEqual([n for n, _ in figure_mentions("如图 2 所示")], ["2"])
        self.assertEqual([n for n, _ in table_mentions("见表 3")], ["3"])

    def test_caption_number(self) -> None:
        self.assertEqual(caption_number("Fig. 2. Profiling of ctDNA"), "2")
        self.assertEqual(caption_number("Figure 10 | Results"), "10")
        self.assertIsNone(caption_number("no number here"))


class FigureNumberFixTests(unittest.TestCase):
    def test_caption_number_wins(self) -> None:
        import sqlite3
        import tempfile
        from pathlib import Path

        from build_db.fix_figure_numbers import fix

        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            conn.execute(
                "CREATE TABLE figures (fig_id TEXT PRIMARY KEY, fig_number TEXT, "
                "caption TEXT, number_conflict INTEGER)"
            )
            conn.execute(
                "INSERT INTO figures VALUES ('f1','Fig 3','Fig. 2. Profiling',NULL)"
            )
            conn.execute(
                "INSERT INTO figures VALUES ('f2','Fig 4','Fig. 4. Same',NULL)"
            )
            conn.commit()
            conn.close()
            stats = fix(db)
            self.assertEqual(stats["corrected"], 1)
            conn = sqlite3.connect(db)
            rows = dict(conn.execute(
                "SELECT fig_id, fig_number || '|' || COALESCE(number_conflict,0) FROM figures"
            ).fetchall())
            conn.close()
            self.assertEqual(rows["f1"], "Fig 2|1")
            self.assertEqual(rows["f2"], "Fig 4|0")


if __name__ == "__main__":
    unittest.main()
