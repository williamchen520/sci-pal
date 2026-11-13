"""Reviewer role permission tests."""

from __future__ import annotations

import unittest

from services.tenancy.pg_service import ROLE_PERMISSIONS
from services.tenancy.schema import ROLES


class ReviewerRoleTests(unittest.TestCase):
    def test_reviewer_role_is_known(self) -> None:
        self.assertIn("reviewer", ROLES)
        self.assertIn("review_evidence", ROLE_PERMISSIONS["reviewer"])

    def test_member_cannot_review(self) -> None:
        self.assertNotIn("review_evidence", ROLE_PERMISSIONS["member"])
        self.assertNotIn("review_evidence", ROLE_PERMISSIONS["viewer"])

    def test_pi_can_review(self) -> None:
        self.assertIn("review_evidence", ROLE_PERMISSIONS["pi"])


if __name__ == "__main__":
    unittest.main()
