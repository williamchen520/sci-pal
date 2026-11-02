from __future__ import annotations

import unittest

from scripts.audit_id_vector_contract import (
    _format,
    _metadata_complete,
    _resolve_summary,
)


class IDVectorAuditHelpersTests(unittest.TestCase):
    def test_format_buckets(self):
        self.assertEqual(_format("para_paper_PMC1_abcd_0001"), "para_paper_*")
        self.assertEqual(_format("paper_PMC1_abcd_para_00001"), "paper_*_para_*")
        self.assertEqual(_format("sec_paper_PMC1_abcd_0001"), "sec_paper_*")
        self.assertEqual(_format("paper_PMC1_abcd_sec_0001"), "paper_*_sec_*")
        self.assertEqual(_format("paper_PMC1_abcd_para_00001_sent_001"), "*_sent_*")
        self.assertEqual(_format("sum_paper_PMC1_abcd_sec_0001"), "sum_*")

    def test_summary_resolution(self):
        sections = {"paper_PMC1_abcd_sec_0001"}
        self.assertEqual(
            _resolve_summary("sum_paper_PMC1_abcd_sec_0001", sections),
            "paper_PMC1_abcd_sec_0001",
        )
        self.assertIsNone(_resolve_summary("sum_missing", sections))

    def test_metadata_presence_allows_empty_optional(self):
        required = ("paper_id", "section_l1", "section_l2")
        self.assertTrue(_metadata_complete({"paper_id": "p", "section_l1": "", "section_l2": ""}, required))
        self.assertFalse(_metadata_complete({"paper_id": "p"}, required))


if __name__ == "__main__":
    unittest.main()
