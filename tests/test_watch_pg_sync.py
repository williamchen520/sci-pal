from __future__ import annotations

import os
import unittest
from unittest import mock

from services.watch import pg_sync


class WatchPGSyncTests(unittest.TestCase):
    def test_enabled_flag(self):
        with mock.patch.dict(
            os.environ,
            {"SCIPAL_WATCH_WRITE_BACKEND": "postgres", "SCIPAL_PG_DSN": "postgresql://x"},
            clear=False,
        ):
            self.assertTrue(pg_sync.enabled())
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_WRITE_BACKEND": ""}, clear=False):
            self.assertFalse(pg_sync.enabled())

    def test_disabled_returns_none(self):
        with mock.patch.object(pg_sync, "enabled", return_value=False):
            self.assertIsNone(pg_sync.sync_pending("unused.db"))


if __name__ == "__main__":
    unittest.main()
