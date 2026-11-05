from __future__ import annotations

import unittest
from unittest import mock

from services.experiments import pg_runs


class _FakePG:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = sql
        return self

    def fetchall(self):
        return [{"run_id": "r1"}]

    def fetchone(self):
        return {"run_id": "r1", "owner_user_id": "u"}

    def commit(self):
        return None

    def close(self):
        return None


class RunsPGBackendTests(unittest.TestCase):
    def test_list(self):
        with mock.patch.object(
            pg_runs.pg_read,
            "get_experiment",
            return_value={"owner_user_id": "u", "protocol_id": "p"},
        ):
            with mock.patch.object(pg_runs, "pg_connection", return_value=_FakePG()):
                rows = pg_runs.list_runs("e1", "w", "u")
        self.assertEqual(rows[0]["run_id"], "r1")

    def test_create_requires_title(self):
        with self.assertRaises(ValueError):
            pg_runs.create_run("e1", "w", "u", "")


if __name__ == "__main__":
    unittest.main()
