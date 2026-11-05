from __future__ import annotations

import unittest
from unittest import mock

from services.experiments import pg_write


class _FakePG:
    def execute(self, *a, **k):
        return self

    def fetchone(self):
        return {"ok": 1}

    def close(self):
        return None


class ExperimentsPGWriteTests(unittest.TestCase):
    def test_create(self):
        with mock.patch.object(pg_write, "pg_connection", return_value=_FakePG()):
            with mock.patch.object(pg_write.pg_read, "_project_access", return_value=True):
                with mock.patch.object(pg_write, "_protocol_exists", return_value=True):
                    with mock.patch.object(pg_write.pg_writes, "create_experiment") as write:
                        with mock.patch.object(
                            pg_write.pg_read,
                            "get_experiment",
                            return_value={"experiment_id": "e1"},
                        ):
                            result = pg_write.create_experiment(
                                "proj",
                                "ws",
                                "u",
                                "Title",
                                protocol_id="p1",
                                protocol_version="v1",
                            )
        self.assertEqual(result["experiment_id"], "e1")
        write.assert_called_once()

    def test_title_required(self):
        with self.assertRaises(ValueError):
            pg_write.create_experiment("p", "w", "u", "", protocol_id="p1", protocol_version="v1")


if __name__ == "__main__":
    unittest.main()

class _RowPG:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        self.sql = sql
        return self

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def close(self):
        return None


class ExperimentsUpdateSignTests(unittest.TestCase):
    def test_update(self):
        with mock.patch.object(
            pg_write, "pg_connection", return_value=_RowPG([
                    {
                        "experiment_id": "e1",
                        "title": "Old",
                        "status": "planned",
                        "protocol_id": "p1",
                        "protocol_version": "v1",
                        "content": "",
                        "current_revision": 1,
                    }
                ])
        ):
            with mock.patch.object(pg_write.pg_writes, "update_experiment") as write:
                with mock.patch.object(
                    pg_write.pg_read, "get_experiment", return_value={"experiment_id": "e1"}
                ):
                    out = pg_write.update_experiment("e1", "w", "u", title="T")
        self.assertEqual(out["experiment_id"], "e1")
        write.assert_called_once()

    def test_sign_requires_password(self):
        with mock.patch.object(
            pg_write,
            "pg_connection",
            return_value=_RowPG([
                    {
                        "experiment_id": "e1",
                        "title": "Old",
                        "status": "planned",
                        "protocol_id": "p1",
                        "protocol_version": "v1",
                        "content": "",
                        "current_revision": 1,
                    }
                ]),
        ):
            with mock.patch.object(pg_write, "verify_password", return_value=False):
                with self.assertRaises(PermissionError):
                    pg_write.sign_experiment("e1", "w", "u", "bad")
