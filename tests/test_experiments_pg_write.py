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
