from __future__ import annotations

import os
import unittest
from unittest import mock

from services.projects import pg_writes


class ProjectPGWritesTests(unittest.TestCase):
    def test_enabled_flag(self):
        with mock.patch.dict(
            os.environ,
            {"SCIPAL_PROJECT_WRITE_BACKEND": "postgres", "SCIPAL_PG_DSN": "postgresql://x"},
            clear=False,
        ):
            self.assertTrue(pg_writes.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_PROJECT_WRITE_BACKEND": ""}, clear=False):
            self.assertFalse(pg_writes.enabled())

    def test_update_empty_is_noop(self):
        self.assertFalse(pg_writes.update_project("p1", "ws1", {}))


if __name__ == "__main__":
    unittest.main()
