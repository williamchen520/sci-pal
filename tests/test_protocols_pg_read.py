from __future__ import annotations

import unittest
from unittest import mock

from services.protocols import pg_read


class _FakePG:
    def execute(self, sql, params=None):
        self.sql = sql
        return self

    def fetchall(self):
        return [{"protocol_id": "p1", "steps": 2}]

    def fetchone(self):
        return {"n": 1}

    def close(self):
        return None


class ProtocolsPGReadTests(unittest.TestCase):
    def test_list(self):
        with mock.patch.object(pg_read, "pg_connection", return_value=_FakePG()):
            rows = pg_read.list_protocols(5)
        self.assertEqual(rows[0]["protocol_id"], "p1")

    def test_count(self):
        with mock.patch.object(pg_read, "pg_connection", return_value=_FakePG()):
            self.assertEqual(pg_read.count_protocols(), 1)


if __name__ == "__main__":
    unittest.main()
