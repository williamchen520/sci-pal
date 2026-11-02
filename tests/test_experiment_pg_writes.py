from __future__ import annotations

import os
import unittest
from unittest import mock

from services.experiments import pg_writes


class ExperimentPGWritesTests(unittest.TestCase):
    def test_enabled_flag(self):
        with mock.patch.dict(
            os.environ,
            {"SCIPAL_EXPERIMENT_WRITE_BACKEND": "postgres", "SCIPAL_PG_DSN": "postgresql://x"},
            clear=False,
        ):
            self.assertTrue(pg_writes.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_EXPERIMENT_WRITE_BACKEND": ""}, clear=False):
            self.assertFalse(pg_writes.enabled())


if __name__ == "__main__":
    unittest.main()
