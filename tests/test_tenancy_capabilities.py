"""E0 capability and resource-scope tests."""

from __future__ import annotations

import unittest

from services.tenancy.capabilities import (
    AccessDenied,
    Principal,
    ResourceScope,
    allowed_federation_scopes,
    can,
    require_capability,
    resolve_federation_scope,
)


def _tenant_owner() -> Principal:
    return Principal(
        user_id="u1",
        memberships={"acme": "owner"},
        library_tenants={"lib_acme": "acme"},
    )


class CapabilityTests(unittest.TestCase):
    def test_platform_owner_has_no_default_tenant_access(self) -> None:
        platform = Principal(user_id="root", platform_role="platform_owner")
        self.assertTrue(can(platform, "platform.plugin.manage", "platform"))
        self.assertFalse(can(platform, "tenant.read", "tenant:acme"))

    def test_tenant_owner_can_import_own_tenant(self) -> None:
        self.assertTrue(can(_tenant_owner(), "tenant.import", "tenant:acme"))

    def test_tenant_owner_cannot_import_other_tenant(self) -> None:
        self.assertFalse(can(_tenant_owner(), "tenant.import", "tenant:other"))

    def test_tenant_owner_cannot_use_platform_capability(self) -> None:
        self.assertFalse(can(_tenant_owner(), "platform.plugin.manage", "platform"))
        self.assertFalse(can(_tenant_owner(), "platform.plugin.manage", "tenant:acme"))

    def test_library_scope_requires_mapping(self) -> None:
        owner = _tenant_owner()
        self.assertTrue(can(owner, "library.write", "library:lib_acme"))
        self.assertFalse(can(owner, "library.write", "library:lib_missing"))
        self.assertFalse(can(owner, "library.write", "library:lib_other"))

    def test_viewer_cannot_import(self) -> None:
        viewer = Principal(
            user_id="u2",
            memberships={"acme": "viewer"},
            library_tenants={"lib_acme": "acme"},
        )
        self.assertTrue(can(viewer, "tenant.read", "tenant:acme"))
        self.assertFalse(can(viewer, "tenant.import", "tenant:acme"))

    def test_federation_scope_is_star_only(self) -> None:
        owner = _tenant_owner()
        self.assertEqual(allowed_federation_scopes(owner, "acme"), ["own"])
        self.assertNotIn("tenant:other", allowed_federation_scopes(owner, "acme"))
        self.assertEqual(resolve_federation_scope(owner, "acme", "own"), ["own"])
        with self.assertRaises(AccessDenied):
            resolve_federation_scope(owner, "acme", "tenant:other")
        with self.assertRaises(AccessDenied):
            resolve_federation_scope(owner, "acme", "main")

    def test_subscribed_main_and_both(self) -> None:
        owner = Principal(
            user_id="u1",
            memberships={"acme": "owner"},
            library_tenants={"lib_acme": "acme"},
            main_subscribed=True,
        )
        self.assertEqual(
            allowed_federation_scopes(owner, "acme"), ["own", "main", "both"]
        )
        self.assertEqual(resolve_federation_scope(owner, "acme", "both"), ["both"])

    def test_unknown_capability_denied(self) -> None:
        self.assertFalse(can(_tenant_owner(), "tenant.delete_all", "tenant:acme"))

    def test_parse_scope(self) -> None:
        self.assertEqual(ResourceScope.parse("platform").kind, "platform")
        self.assertEqual(ResourceScope.parse("tenant:acme").id, "acme")
        self.assertEqual(ResourceScope.parse("library:lib_1").kind, "library")
        with self.assertRaises(ValueError):
            ResourceScope.parse("tenant:")

    def test_require_raises(self) -> None:
        with self.assertRaises(AccessDenied):
            require_capability(_tenant_owner(), "tenant.import", "tenant:other")


if __name__ == "__main__":
    unittest.main()
