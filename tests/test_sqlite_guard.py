"""SQLite runtime guard tests."""

from __future__ import annotations

import os
import sqlite3
import unittest
from unittest import mock

from services.db import sqlite_guard


class SQLiteGuardTests(unittest.TestCase):
    def test_runtime_disabled_values(self) -> None:
        for value in ("0", "false", "off", "deny"):
            with mock.patch.dict(os.environ, {"SCIPAL_SQLITE_RUNTIME": value}):
                self.assertTrue(sqlite_guard.runtime_disabled())
        with mock.patch.dict(os.environ, {"SCIPAL_SQLITE_RUNTIME": "1"}):
            self.assertFalse(sqlite_guard.runtime_disabled())

    def test_install_denies_connect(self) -> None:
        original = sqlite3.connect
        sqlite_guard._INSTALLED = False
        try:
            with mock.patch.dict(os.environ, {"SCIPAL_SQLITE_RUNTIME": "0"}):
                sqlite_guard.install_sqlite_guard()
                with self.assertRaises(RuntimeError):
                    sqlite3.connect(":memory:")
        finally:
            sqlite3.connect = original
            sqlite_guard._INSTALLED = False


if __name__ == "__main__":
    unittest.main()
