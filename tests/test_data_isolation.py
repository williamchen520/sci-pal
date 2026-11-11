"""Physical data-layer isolation contract tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.db import pg_pool


class ConnectionSplitTests(unittest.TestCase):
    def test_core_and_corpus_use_distinct_dsns(self) -> None:
        env = {
            "SCIPAL_CORE_DSN": "postgresql://core",
            "SCIPAL_PG_CORPUS_DSN": "postgresql://corpus",
            "SCIPAL_PG_DSN": "postgresql://core",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(pg_pool, "pg_connection", side_effect=lambda dsn: dsn):
                self.assertEqual(pg_pool.core_connection(), "postgresql://core")
                self.assertEqual(pg_pool.corpus_connection(), "postgresql://corpus")

    def test_business_connections_never_use_corpus_dsn(self) -> None:
        env = {
            "SCIPAL_CORE_DSN": "postgresql://core",
            "SCIPAL_PG_CORPUS_DSN": "postgresql://corpus",
            "SCIPAL_PG_DSN": "postgresql://core",
            "SCIPAL_PG_ADMIN_DSN": "postgresql://core",
            "SCIPAL_PG_TENANT_WRITE_DSN": "postgresql://core",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(pg_pool, "pg_connection", side_effect=lambda dsn: dsn):
                self.assertEqual(pg_pool.admin_connection(), "postgresql://core")
                self.assertEqual(pg_pool.tenant_write_connection(), "postgresql://core")

    def test_auth_uses_auth_or_core_dsn(self) -> None:
        env = {
            "SCIPAL_AUTH_DSN": "postgresql://auth",
            "SCIPAL_CORE_DSN": "postgresql://core",
            "SCIPAL_PG_CORPUS_DSN": "postgresql://corpus",
        }
        class FakeConn:
            def __init__(self, dsn):
                self.dsn = dsn

            def execute(self, *args, **kwargs):
                return self

        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(pg_pool, "pg_connection", side_effect=lambda dsn: FakeConn(dsn)):
                self.assertEqual(pg_pool.auth_connection().dsn, "postgresql://auth")
        env.pop("SCIPAL_AUTH_DSN")
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(pg_pool, "pg_connection", side_effect=lambda dsn: FakeConn(dsn)):
                self.assertEqual(pg_pool.auth_connection().dsn, "postgresql://core")

    def test_corpus_writes_never_use_core_dsn(self) -> None:
        env = {
            "SCIPAL_CORE_DSN": "postgresql://core",
            "SCIPAL_PG_CORPUS_DSN": "postgresql://corpus",
            "SCIPAL_PG_INGEST_DSN": "postgresql://corpus",
            "SCIPAL_PG_OWNER_DSN": "postgresql://corpus",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(pg_pool, "pg_connection", side_effect=lambda dsn: dsn):
                self.assertEqual(pg_pool.ingest_connection(), "postgresql://corpus")
                self.assertEqual(pg_pool.owner_connection(), "postgresql://corpus")


if __name__ == "__main__":
    unittest.main()


class FakeConn:
    def __init__(self, dbname: str) -> None:
        self.dbname = dbname

    def execute(self, *args, **kwargs):
        return self

    def fetchone(self):
        return {"ok": 1}

    def fetchall(self):
        return [{"paper_id": "p1", "cnt": 1}]

    def commit(self):
        return None

    def close(self):
        return None


class PaperStoreOwnershipTests(unittest.TestCase):
    def test_paper_reads_use_corpus(self) -> None:
        from services.papers import paper_store

        calls = []

        def read():
            calls.append("corpus")
            return FakeConn("scipal_rebuild")

        with mock.patch.object(paper_store, "main_read_connection", side_effect=read):
            store = paper_store.PaperStore()
            self.assertTrue(store.exists("p1"))
            self.assertTrue(store.filename("p1"))
            self.assertTrue(store.in_workspace("p1", "ws_default"))
            self.assertEqual(store.supplementary_counts(), {"p1": 1})

        self.assertEqual(calls, ["corpus", "corpus", "corpus", "corpus"])

    def test_workspace_write_uses_corpus_owner(self) -> None:
        from services.papers import paper_store

        seen = []

        def owner():
            seen.append("owner")
            return FakeConn("scipal_rebuild")

        with mock.patch.object(paper_store, "owner_connection", side_effect=owner):
            paper_store.PaperStore().assign_workspace("p1", "ws_default")

        self.assertEqual(seen, ["owner"])
