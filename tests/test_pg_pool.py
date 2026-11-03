from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.db.pg_pool import PooledConnection, pg_connection, pool_settings


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self):
        self.returned = []

    def putconn(self, conn):
        self.returned.append(conn)


class PgPoolTests(unittest.TestCase):
    def test_settings_from_env(self):
        with patch.dict(
            os.environ,
            {"SCIPAL_PG_POOL_MIN": "2", "SCIPAL_PG_POOL_MAX": "24", "SCIPAL_PG_POOL_TIMEOUT": "3.5"},
        ):
            cfg = pool_settings()
        self.assertEqual(cfg["min_size"], 2)
        self.assertEqual(cfg["max_size"], 24)
        self.assertEqual(cfg["timeout"], 3.5)

    def test_lease_commits_and_returns_to_pool(self):
        pool, conn = FakePool(), FakeConnection()
        with PooledConnection(pool, conn) as lease:
            self.assertIs(lease._conn, conn)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(pool.returned, [conn])

    def test_lease_rolls_back_on_error(self):
        pool, conn = FakePool(), FakeConnection()
        with self.assertRaises(RuntimeError):
            with PooledConnection(pool, conn):
                raise RuntimeError("boom")
        self.assertEqual(conn.rollbacks, 1)
        self.assertEqual(pool.returned, [conn])

    def test_requires_dsn(self):
        with patch.dict(os.environ, {"SCIPAL_PG_DSN": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                pg_connection()


if __name__ == "__main__":
    unittest.main()
