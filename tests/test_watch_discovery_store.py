from __future__ import annotations

import os
import unittest
from unittest import mock

from services.watch import discovery, pg_store, repo


class WatchDiscoveryStoreTests(unittest.TestCase):
    def test_default_repo(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SCIPAL_WATCH_PG_STORE", None)
            self.assertIs(discovery._store(), repo)

    def test_pg_store_flag(self):
        with mock.patch.dict(os.environ, {"SCIPAL_WATCH_PG_STORE": "postgres"}):
            self.assertIs(discovery._store(), pg_store)


if __name__ == "__main__":
    unittest.main()
