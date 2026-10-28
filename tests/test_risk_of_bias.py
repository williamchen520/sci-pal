"""Risk-of-bias heuristic tests."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from build_db.review_schema import migrate
from services.review import risk_of_bias


class RiskOfBiasTests(unittest.TestCase):
    def test_low_risk_trial(self) -> None:
        rows = risk_of_bias.assess(
            "Randomized double-blind placebo-controlled trial. "
            "Overall survival was measured. The trial was registered."
        )
        mapping = {row["domain"]: row["judgement"] for row in rows}
        self.assertEqual(mapping["randomization"], "low")
        self.assertEqual(mapping["deviations"], "low")
        self.assertEqual(mapping["measurement"], "low")
        self.assertEqual(risk_of_bias.overall(rows), "low")

    def test_high_risk_observational(self) -> None:
        rows = risk_of_bias.assess(
            "Retrospective observational single-arm study with missing data and lost to follow-up."
        )
        mapping = {row["domain"]: row["judgement"] for row in rows}
        self.assertEqual(mapping["randomization"], "high")
        self.assertEqual(risk_of_bias.overall(rows), "high")

    def test_save_and_list(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        db = Path(tmp.name) / "t.db"
        migrate(db)
        conn = sqlite3.connect(db)
        rows = risk_of_bias.assess("Randomized trial with overall survival.")
        risk_of_bias.save(conn, "p1", "paper1", rows)
        listed = risk_of_bias.list_rows(conn, "p1")
        conn.close()
        self.assertEqual(len(listed), 5)
        self.assertEqual(listed[0]["paper_id"], "paper1")


if __name__ == "__main__":
    unittest.main()
