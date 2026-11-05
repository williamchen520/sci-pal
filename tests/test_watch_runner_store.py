from __future__ import annotations

import os
import unittest
from unittest import mock

from services.watch import pg_store, repo, runner


class WatchRunnerStoreTests(unittest.TestCase):
    def test_default_repo(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCIPAL_WATCH_PG_STORE", None)
            self.assertIs(runner._store(), repo)

    def test_pg_store_flag(self):
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_PG_STORE": "postgres"}):
            self.assertIs(runner._store(), pg_store)
            self.assertTrue(runner._pg_mode())


if __name__ == "__main__":
    unittest.main()
