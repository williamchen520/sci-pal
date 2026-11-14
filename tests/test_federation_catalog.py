"""E1 federation catalog tests."""

from __future__ import annotations

import unittest
from unittest import mock

from services.federation import catalog
from services.tenancy.capabilities import AccessDenied, Principal


def _platform() -> Principal:
    return Principal(user_id="root", platform_role="platform_owner")


def _owner() -> Principal:
    return Principal(
        user_id="u1",
        memberships={"acme": "owner"},
        library_tenants={"lib_acme": "acme"},
        main_subscribed=True,
    )


class CatalogTests(unittest.TestCase):
    def test_register_requires_platform(self) -> None:
        with self.assertRaises(AccessDenied):
            catalog.register_main_link(
                _owner(), tenant_id="acme", library_id="lib_acme", allowed_scopes=["own"]
            )

    def test_register_platform_only_main(self) -> None:
        with mock.patch.object(
            catalog, "_upsert_link", return_value={"catalog_id": "fed_1", "target_kind": "main"}
        ) as upsert:
            result = catalog.register_main_link(
                _platform(),
                tenant_id="acme",
                library_id="lib_acme",
                allowed_scopes=["own", "main"],
            )
        self.assertEqual(result["target_kind"], "main")
        self.assertEqual(upsert.call_args.kwargs["allowed_scopes"], ["main", "own"])

    def test_peer_target_rejected(self) -> None:
        with self.assertRaises(catalog.FederationError):
            catalog.assert_star_target("tenant", "other")
        with self.assertRaises(catalog.FederationError):
            catalog.assert_star_target("main", "other")

    def test_invalid_scope_rejected(self) -> None:
        with self.assertRaises(catalog.FederationError):
            catalog.register_main_link(
                _platform(),
                tenant_id="acme",
                library_id="lib_acme",
                allowed_scopes=["tenant:other"],
            )

    def test_list_only_own_tenant(self) -> None:
        with mock.patch.object(
            catalog, "_query_links", return_value=[{"library_id": "lib_acme"}]
        ):
            rows = catalog.list_links(_owner(), "acme")
        self.assertEqual(rows[0]["library_id"], "lib_acme")
        with self.assertRaises(AccessDenied):
            catalog.list_links(_owner(), "other")

    def test_platform_cannot_list_tenant(self) -> None:
        with self.assertRaises(AccessDenied):
            catalog.list_links(_platform(), "acme")

    def test_resolve_requires_catalog_for_main(self) -> None:
        with mock.patch.object(catalog, "_fetch_link", return_value=None):
            self.assertEqual(catalog.resolve_catalog_scope(_owner(), "acme", "own"), "own")
            with self.assertRaises(AccessDenied):
                catalog.resolve_catalog_scope(_owner(), "acme", "main")

    def test_resolve_main_with_link(self) -> None:
        with mock.patch.object(
            catalog, "_fetch_link", return_value={"allowed_scopes": ["own", "main", "both"]}
        ):
            self.assertEqual(catalog.resolve_catalog_scope(_owner(), "acme", "both"), "both")

    def test_peer_scope_rejected(self) -> None:
        with self.assertRaises(AccessDenied):
            catalog.resolve_catalog_scope(_owner(), "acme", "tenant:other")


if __name__ == "__main__":
    unittest.main()
