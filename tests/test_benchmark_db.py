"""Benchmark backend policy tests."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.quality.benchmark_db import (
    ALLOW_SQLITE_ENV,
    BenchmarkDBError,
    ensure_benchmark_backend,
)


class BenchmarkDBPolicyTests(unittest.TestCase):
    def test_default_is_postgres_and_requires_driver(self) -> None:
        with patch.dict(os.environ, {}, clear=False), patch(
            "services.quality.benchmark_db._has_postgres_driver", return_value=False
        ):
            os.environ.pop("SCIPAL_BENCH_DATABASE_URL", None)
            with self.assertRaises(BenchmarkDBError):
                ensure_benchmark_backend()

    def test_postgres_with_driver_passes(self) -> None:
        with patch.dict(
            os.environ,
            {"SCIPAL_BENCH_DATABASE_URL": "postgresql://u:p@localhost/db"},
            clear=False,
        ), patch(
            "services.quality.benchmark_db._has_postgres_driver", return_value=True
        ):
            self.assertIn("postgresql://", ensure_benchmark_backend())

    def test_sqlite_small_requires_opt_in(self) -> None:
        with patch.dict(
            os.environ,
            {"SCIPAL_BENCH_DATABASE_URL": "sqlite:///tmp/bench.db"},
            clear=False,
        ):
            os.environ.pop(ALLOW_SQLITE_ENV, None)
            with self.assertRaises(BenchmarkDBError):
                ensure_benchmark_backend(papers=10)

    def test_sqlite_small_with_opt_in_passes(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SCIPAL_BENCH_DATABASE_URL": "sqlite:///tmp/bench.db",
                ALLOW_SQLITE_ENV: "1",
            },
            clear=False,
        ):
            self.assertIn("sqlite", ensure_benchmark_backend(papers=10))

    def test_sqlite_large_is_forbidden_even_with_opt_in(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SCIPAL_BENCH_DATABASE_URL": "sqlite:///tmp/bench.db",
                ALLOW_SQLITE_ENV: "1",
            },
            clear=False,
        ):
            with self.assertRaises(BenchmarkDBError):
                ensure_benchmark_backend(papers=101)

    def test_sqlite_concurrent_is_forbidden(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SCIPAL_BENCH_DATABASE_URL": "sqlite:///tmp/bench.db",
                ALLOW_SQLITE_ENV: "1",
            },
            clear=False,
        ):
            with self.assertRaises(BenchmarkDBError):
                ensure_benchmark_backend(papers=10, concurrent=2)


if __name__ == "__main__":
    unittest.main()
