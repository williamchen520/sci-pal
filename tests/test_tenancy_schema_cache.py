"""Tenancy schema cache/concurrency tests."""

from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from services.tenancy.schema import _SCHEMA_READY, ensure_schema


class TenancySchemaCacheTests(unittest.TestCase):
    def test_schema_is_cached_per_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            conn = sqlite3.connect(db)
            try:
                ensure_schema(conn)
                self.assertIn(str(db), _SCHEMA_READY)
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM sqlite_master WHERE name='memberships'"
                    ).fetchone()[0],
                    1,
                )
                ensure_schema(conn)
            finally:
                conn.close()

    def test_concurrent_first_calls_do_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "t.db"
            errors = []

            def worker() -> None:
                try:
                    conn = sqlite3.connect(db, timeout=30)
                    try:
                        ensure_schema(conn)
                    finally:
                        conn.close()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(20)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
