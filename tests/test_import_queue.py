"""U1 import queue tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.imports import queue


class QueueTests(unittest.TestCase):
    def test_run_once_claims_and_processes(self) -> None:
        with mock.patch.object(queue, "claim_next", return_value="imp_1"), mock.patch.object(
            queue, "process_import", return_value={"import_id": "imp_1", "status": "completed"}
        ) as process:
            result = queue.run_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(process.call_args.args[0], "imp_1")

    def test_no_work(self) -> None:
        with mock.patch.object(queue, "claim_next", return_value=None):
            self.assertIsNone(queue.run_once())

    def test_requeue(self) -> None:
        class _Cursor:
            def fetchone(self):
                return {"import_id": "imp_1", "status": "queued"}

        class _Conn:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, *args, **kwargs):
                return _Cursor()

        with mock.patch.object(queue, "core_connection", return_value=_Conn()):
            self.assertEqual(queue.requeue("imp_1")["status"], "queued")


if __name__ == "__main__":
    unittest.main()
