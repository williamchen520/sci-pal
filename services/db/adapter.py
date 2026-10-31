"""Database adapter layer (P1).

SQLite remains the default. PostgreSQL is opt-in via ``SCIPAL_DB_BACKEND``.
This module only provides connections/transactions; it does not migrate data.
"""

from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SQLITE = PROJECT_ROOT / "data" / "research.db"


class DBAdapterError(RuntimeError):
    """Raised when the configured backend cannot be used."""


@dataclass(frozen=True)
class DBConfig:
    backend: str = "sqlite"
    sqlite_path: Path = DEFAULT_SQLITE
    pg_dsn: str = ""
    pool_min: int = 1
    pool_max: int = 10

    @classmethod
    def from_env(cls) -> "DBConfig":
        backend = (os.environ.get("SCIPAL_DB_BACKEND") or "sqlite").strip().lower()
        sqlite_path = Path(
            os.environ.get("SCIPAL_SQLITE_PATH") or DEFAULT_SQLITE
        )
        return cls(
            backend=backend,
            sqlite_path=sqlite_path,
            pg_dsn=os.environ.get("SCIPAL_PG_DSN") or "",
            pool_min=int(os.environ.get("SCIPAL_PG_POOL_MIN") or 1),
            pool_max=int(os.environ.get("SCIPAL_PG_POOL_MAX") or 10),
        )


class DBAdapter(ABC):
    backend: str

    @abstractmethod
    def connect(self) -> Any:
        ...

    @contextmanager
    def session(self) -> Iterator[Any]:
        conn = self.connect()
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @abstractmethod
    def healthcheck(self) -> dict:
        ...


class SQLiteAdapter(DBAdapter):
    backend = "sqlite"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def healthcheck(self) -> dict:
        with self.session() as conn:
            tables = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            return {"backend": "sqlite", "path": str(self.path), "tables": tables}


class PostgresAdapter(DBAdapter):
    backend = "postgres"

    def __init__(self, dsn: str, *, connector=None):
        self.dsn = dsn
        self._connector = connector

    def _connect(self) -> Any:
        if self._connector is not None:
            return self._connector()
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise DBAdapterError(
                "psycopg is required for SCIPAL_DB_BACKEND=postgres; "
                "install psycopg[binary]"
            ) from exc
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def connect(self) -> Any:
        return self._connect()

    def healthcheck(self) -> dict:
        with self.session() as conn:
            row = conn.execute("SELECT current_database() AS db").fetchone()
            db = row["db"] if isinstance(row, dict) else row[0]
            return {"backend": "postgres", "database": db}


def create_adapter(config: Optional[DBConfig] = None) -> DBAdapter:
    config = config or DBConfig.from_env()
    if config.backend == "sqlite":
        return SQLiteAdapter(config.sqlite_path)
    if config.backend in {"postgres", "postgresql"}:
        if not config.pg_dsn:
            raise DBAdapterError("SCIPAL_PG_DSN is required for PostgreSQL backend")
        return PostgresAdapter(config.pg_dsn)
    raise DBAdapterError(f"unknown database backend: {config.backend}")
