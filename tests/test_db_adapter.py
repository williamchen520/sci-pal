"""P1 database adapter tests."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.db import (
    DBAdapterError,
    DBConfig,
    PostgresAdapter,
    SQLiteAdapter,
    create_adapter,
)


class FakePostgresConnection:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, *args):
        return self

    def fetchone(self):
        return {"db": "scipal_test"}

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class DBAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "test.db"

    def test_sqlite_transaction_commit_and_rollback(self) -> None:
        adapter = SQLiteAdapter(self.db)
        with adapter.transaction() as conn:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO t (name) VALUES ('ok')")
        with adapter.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        with self.assertRaises(RuntimeError):
            with adapter.transaction() as conn:
                conn.execute("INSERT INTO t (name) VALUES ('bad')")
                raise RuntimeError("rollback")
        with adapter.session() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)

    def test_sqlite_healthcheck(self) -> None:
        adapter = SQLiteAdapter(self.db)
        with adapter.session() as conn:
            conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
            conn.commit()
        self.assertEqual(adapter.healthcheck()["tables"], 1)

    def test_postgres_uses_injected_connector(self) -> None:
        fake = FakePostgresConnection()
        adapter = PostgresAdapter("postgresql://example", connector=lambda: fake)
        self.assertIs(adapter.connect(), fake)
        self.assertEqual(adapter.healthcheck()["database"], "scipal_test")
        self.assertTrue(fake.closed)

    def test_create_adapter_defaults_to_sqlite(self) -> None:
        adapter = create_adapter(DBConfig(backend="sqlite", sqlite_path=self.db))
        self.assertIsInstance(adapter, SQLiteAdapter)

    def test_unknown_backend_is_rejected(self) -> None:
        with self.assertRaises(DBAdapterError):
            create_adapter(DBConfig(backend="mysql", sqlite_path=self.db))

    def test_postgres_requires_dsn(self) -> None:
        with self.assertRaises(DBAdapterError):
            create_adapter(DBConfig(backend="postgres", pg_dsn=""))

    def test_config_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SCIPAL_DB_BACKEND": "postgres",
                "SCIPAL_PG_DSN": "postgresql://u:p@h/db",
                "SCIPAL_PG_POOL_MAX": "5",
            },
            clear=False,
        ):
            cfg = DBConfig.from_env()
            self.assertEqual(cfg.backend, "postgres")
            self.assertEqual(cfg.pg_dsn, "postgresql://u:p@h/db")
            self.assertEqual(cfg.pool_max, 5)


class PostgresSchemaTests(unittest.TestCase):
    def test_schema_has_core_tables_and_fts(self) -> None:
        schema = (
            Path(__file__).resolve().parent.parent / "build_db" / "postgres_schema.sql"
        ).read_text(encoding="utf-8")
        for table in ("papers", "paragraphs", "sentences", "claim_cards", "watch_items"):
            self.assertIn(f'CREATE TABLE IF NOT EXISTS "{table}"', schema)
        self.assertIn("search_vector tsvector", schema)
        self.assertIn("USING GIN (search_vector)", schema)


if __name__ == "__main__":
    unittest.main()
