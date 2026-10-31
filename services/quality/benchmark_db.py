"""Benchmark database policy (Route B).

High-volume or concurrent benchmarks must use PostgreSQL. SQLite is allowed only
for small local checks with an explicit opt-in.

This module does not provide a PostgreSQL backend; it fails fast so a benchmark
cannot silently run at scale on SQLite.
"""

from __future__ import annotations

import importlib.util
import os
from urllib.parse import urlparse

DEFAULT_BENCH_DATABASE_URL = "postgresql://scipal:scipal@127.0.0.1:5432/scipal_bench"
ALLOW_SQLITE_ENV = "SCIPAL_BENCH_ALLOW_SQLITE"
URL_ENV = "SCIPAL_BENCH_DATABASE_URL"
LARGE_THRESHOLD = 100


class BenchmarkDBError(RuntimeError):
    """Raised when a benchmark backend violates the policy."""


def benchmark_database_url() -> str:
    return os.environ.get(URL_ENV) or DEFAULT_BENCH_DATABASE_URL


def _scheme(url: str) -> str:
    return urlparse(url).scheme.lower()


def _has_postgres_driver() -> bool:
    return bool(
        importlib.util.find_spec("psycopg")
        or importlib.util.find_spec("psycopg2")
    )


def ensure_benchmark_backend(*, papers: int = 0, concurrent: int = 1) -> str:
    """Validate the benchmark backend, or raise with a clear remediation.

    - PostgreSQL URL: accepted only if a driver is installed.
    - SQLite URL: accepted only for <=100 papers, single-worker, and explicit
      ``SCIPAL_BENCH_ALLOW_SQLITE=1``.
    - Large/concurrent benchmark: PostgreSQL only, no SQLite override.
    """
    url = benchmark_database_url()
    scheme = _scheme(url)
    large = int(papers) > LARGE_THRESHOLD
    concurrent_run = int(concurrent) > 1

    if scheme not in {"postgres", "postgresql", "sqlite"}:
        raise BenchmarkDBError(
            f"unsupported benchmark database scheme: {scheme or '<empty>'}; "
            "use postgresql://"
        )

    if scheme in {"postgres", "postgresql"}:
        if not _has_postgres_driver():
            raise BenchmarkDBError(
                "PostgreSQL benchmark backend selected but no driver is installed; "
                "install 'psycopg[binary]' or use a small local SQLite run with "
                f"{ALLOW_SQLITE_ENV}=1"
            )
        return url

    if large or concurrent_run:
        raise BenchmarkDBError(
            "大规模（>100 篇）测试或并发测试必须使用 PostgreSQL；"
            "严禁使用 SQLite 进行高并发测试。"
        )
    if os.environ.get(ALLOW_SQLITE_ENV) != "1":
        raise BenchmarkDBError(
            "SQLite benchmark requires explicit opt-in: "
            f"set {ALLOW_SQLITE_ENV}=1 for local small tests only."
        )
    return url


def describe_backend(*, papers: int = 0, concurrent: int = 1) -> dict:
    url = ensure_benchmark_backend(papers=papers, concurrent=concurrent)
    scheme = _scheme(url)
    return {
        "url": url,
        "scheme": scheme,
        "papers": int(papers),
        "concurrent": int(concurrent),
        "policy": "postgresql-required-for-large-or-concurrent",
    }
