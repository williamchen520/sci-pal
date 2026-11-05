from __future__ import annotations

import os
import unittest
from unittest import mock

from services.projects import pg_service


class ProjectsPGBackendTests(unittest.TestCase):
    def test_enabled(self):
        with mock.patch.dict(os.environ, {"SCIPAL_PROJECTS_BACKEND": "postgres"}):
            self.assertTrue(pg_service.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_PROJECTS_BACKEND": ""}):
            self.assertFalse(pg_service.enabled())

    def test_visibility(self):
        self.assertTrue(pg_service._can_see_all("owner"))
        self.assertTrue(pg_service._can_see_all("pi"))
        self.assertFalse(pg_service._can_see_all("member"))


if __name__ == "__main__":
    unittest.main()
