"""Tests for the CI wrapper's approval semantics."""

from __future__ import annotations

import unittest

from scripts.governance_ci import APPROVAL_LABEL, approved


class GovernanceCIApprovalTests(unittest.TestCase):
    def test_label_is_required(self) -> None:
        self.assertFalse(approved(""))
        self.assertFalse(approved("bug,enhancement"))

    def test_label_with_spaces(self) -> None:
        self.assertTrue(approved(f"bug, {APPROVAL_LABEL}, docs"))

    def test_exact_label_only(self) -> None:
        self.assertFalse(approved("governance-approved-but-not-really"))


if __name__ == "__main__":
    unittest.main()
