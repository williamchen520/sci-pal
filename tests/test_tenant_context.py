"""S0 TenantContext tests."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from services.tenancy import context


class TenantContextTests(unittest.TestCase):
    def test_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            ctx = context.context_from_env()
        self.assertEqual(ctx.tenant_id, "default")
        self.assertTrue(ctx.main_federation_enabled)
        self.assertEqual(ctx.index_prefix, "tenant:default:")
        self.assertEqual(ctx.source_schemas, ("xml", "html", "pdf"))
        self.assertTrue(ctx.storage_root.endswith("data\\tenants\\default"))

    def test_explicit_tenant_and_main_off(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "SCIPAL_TENANT_STORAGE_ROOT": "D:\\tmp\\tenants",
                "SCIPAL_TENANT_MAIN_FEDERATION": "0",
            },
            clear=True,
        ):
            ctx = context.context_from_env("acme")
        self.assertEqual(ctx.tenant_id, "acme")
        self.assertFalse(ctx.main_federation_enabled)
        self.assertTrue(ctx.storage_root.endswith("D:\\tmp\\tenants"))
        self.assertEqual(ctx.index_prefix, "tenant:acme:")

    def test_resolve_corpus_dsn(self) -> None:
        with mock.patch.dict(
            os.environ, {"SCIPAL_TENANT_DB_DSN": "postgresql://tenant/db"}, clear=True
        ):
            ctx = context.context_from_env()
            self.assertEqual(ctx.resolve_dsn("corpus"), "postgresql://tenant/db")

    def test_resolve_code_fallback(self) -> None:
        with mock.patch.dict(
            os.environ, {"SCIPAL_CODE_READ_DSN": "postgresql://code/db"}, clear=True
        ):
            ctx = context.context_from_env()
            self.assertEqual(ctx.resolve_dsn("code"), "postgresql://code/db")

    def test_missing_dsn(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            ctx = context.context_from_env()
            with self.assertRaises(context.TenantContextError):
                ctx.resolve_dsn("corpus")

    def test_connection_uses_pg_connection(self) -> None:
        with mock.patch.dict(
            os.environ, {"SCIPAL_TENANT_DB_DSN": "postgresql://tenant/db"}, clear=True
        ), mock.patch("services.db.pg_pool.pg_connection") as pg:
            ctx = context.context_from_env()
            ctx.connection("corpus")
        pg.assert_called_once_with("postgresql://tenant/db")

    def test_federation_scopes(self) -> None:
        with mock.patch.dict(os.environ, {"SCIPAL_TENANT_MAIN_FEDERATION": "0"}, clear=True):
            ctx = context.context_from_env()
        self.assertTrue(ctx.allows_federation_scope("own"))
        self.assertFalse(ctx.allows_federation_scope("main"))
        self.assertFalse(ctx.allows_federation_scope("both"))
        self.assertFalse(ctx.allows_federation_scope("tenant:other"))

    def test_public_dict_has_no_dsn(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            data = context.context_from_env().public_dict()
        self.assertNotIn("postgresql", str(data))
        self.assertEqual(data["database_dsn_ref"], "SCIPAL_TENANT_DB_DSN")
        self.assertEqual(data["tenant_id"], "default")

    def test_two_tenants_have_distinct_prefixes(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            a = context.context_from_env("tenant-a")
            b = context.context_from_env("tenant-b")
        self.assertNotEqual(a.index_prefix, b.index_prefix)
        self.assertNotEqual(a.storage_root, b.storage_root)


if __name__ == "__main__":
    unittest.main()
