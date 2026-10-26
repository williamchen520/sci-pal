"""Cross-store task lookup tests."""

from __future__ import annotations

import unittest

from services.task_lookup import lookup_task


class TaskLookupTests(unittest.TestCase):
    def test_first_store_wins(self) -> None:
        result = lookup_task(
            "t1",
            unified=lambda task_id: {"task_id": task_id, "status": "running"},
            review=lambda task_id: {"task_id": task_id, "status": "completed"},
        )
        self.assertEqual(result["source"], "unified")
        self.assertEqual(result["task"]["status"], "running")

    def test_falls_through_to_next_store(self) -> None:
        result = lookup_task(
            "t2",
            unified=lambda task_id: None,
            review=lambda task_id: {"task_id": task_id, "status": "completed"},
        )
        self.assertEqual(result["source"], "review")

    def test_broken_store_is_skipped(self) -> None:
        def broken(task_id):
            raise RuntimeError("store down")

        result = lookup_task(
            "t3",
            unified=broken,
            ingest=lambda task_id: {"task_id": task_id, "status": "partial"},
        )
        self.assertEqual(result["source"], "ingest")

    def test_unknown_returns_none(self) -> None:
        self.assertIsNone(
            lookup_task("missing", unified=lambda _: None, review=lambda _: None,
                        export=lambda _: None, ingest=lambda _: None)
        )


if __name__ == "__main__":
    unittest.main()
