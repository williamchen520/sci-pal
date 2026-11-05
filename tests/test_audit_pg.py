from __future__ import annotations

import os
import unittest
from unittest import mock

from services.data_sandbox import audit


class _FakePG:
    def __init__(self):
        self.sql = ""
        self.params = None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        return self

    def fetchall(self):
        return [{"id": 1, "owner": "o"}]

    def commit(self):
        return None

    def close(self):
        return None


class AuditPGBackendTests(unittest.TestCase):
    def test_log_uses_pg(self):
        pg = _FakePG()
        with mock.patch.dict(os.environ, {"SCIPAL_AUDIT_BACKEND": "postgres"}):
            with mock.patch("services.db.pg_pool.pg_connection", return_value=pg):
                audit.log_event(owner="o", project_id="p", action="a")
        self.assertIn("INSERT INTO data_audit", pg.sql)
        self.assertEqual(pg.params[0], "o")

    def test_list_uses_pg(self):
        pg = _FakePG()
        with mock.patch.dict(os.environ, {"SCIPAL_AUDIT_BACKEND": "postgres"}):
            with mock.patch("services.db.pg_pool.pg_connection", return_value=pg):
                rows = audit.list_events("o")
        self.assertEqual(rows[0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
