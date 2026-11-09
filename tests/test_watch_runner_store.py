from __future__ import annotations

import os
import unittest
from unittest import mock

from services.watch import pg_store, runner


class WatchRunnerStoreTests(unittest.TestCase):
    def test_store_is_pg(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            self.assertIs(runner._store(), pg_store)


if __name__ == "__main__":
    unittest.main()
