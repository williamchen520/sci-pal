from __future__ import annotations

import os

os.environ.setdefault("SCIPAL_WATCH_ALLOW_SQLITE_REPO", "1")

import os
import unittest
from unittest import mock

from services.watch import pg_store, repo, runner


class WatchRunnerStoreTests(unittest.TestCase):
    def test_default_repo(self):
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_ALLOW_SQLITE_REPO": "1"}):
            self.assertIs(runner._store(), repo)

    def test_pg_store_flag(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCIPAL_WATCH_ALLOW_SQLITE_REPO", None)
            self.assertIs(runner._store(), pg_store)


if __name__ == "__main__":
    unittest.main()
