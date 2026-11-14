"""E2 tenant provisioning tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.tenancy import provisioning
from services.tenancy.capabilities import AccessDenied, Principal


def _platform() -> Principal:
    return Principal(user_id="root", platform_role="platform_owner")


def _owner() -> Principal:
    return Principal(user_id="u1", memberships={"acme": "owner"})


class ProvisioningTests(unittest.TestCase):
    def test_plan_is_deterministic(self) -> None:
        plan = provisioning.stack_plan("Acme-Labs")
        self.assertEqual(plan["tenant_id"], "acme-labs")
        self.assertEqual(plan["database_name"], "scipal_tenant_acme-labs")
        self.assertEqual(plan["index_prefix"], "tenant:acme-labs:")
        self.assertEqual(plan["code_schema"], "code")

    def test_invalid_tenant(self) -> None:
        with self.assertRaises(provisioning.ProvisioningError):
            provisioning.stack_plan("../etc")

    def test_non_platform_denied(self) -> None:
        with self.assertRaises(AccessDenied):
            provisioning.provision_tenant(_owner(), "acme")

    def test_provision_records_planned_and_creates_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            provisioning, "storage_root", return_value=Path(tmp)
        ), mock.patch.object(
            provisioning,
            "_upsert_stack",
            return_value={"tenant_id": "acme", "status": "planned"},
        ):
            row = provisioning.provision_tenant(_platform(), "acme")
            self.assertTrue((Path(tmp) / "acme").is_dir())
        self.assertEqual(row["status"], "planned")

    def test_repeated_provision_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            provisioning, "storage_root", return_value=Path(tmp)
        ), mock.patch.object(
            provisioning,
            "_upsert_stack",
            return_value={"tenant_id": "acme", "status": "provisioned"},
        ):
            first = provisioning.provision_tenant(_platform(), "acme")
            second = provisioning.provision_tenant(_platform(), "acme")
        self.assertEqual(first["status"], "provisioned")
        self.assertEqual(second["status"], "provisioned")

    def test_get_stack_tenant_scope(self) -> None:
        with mock.patch.object(
            provisioning,
            "core_connection",
            return_value=mock.MagicMock(
                __enter__=mock.MagicMock(return_value=mock.Mock(
                    execute=mock.Mock(return_value=mock.Mock(
                        fetchone=mock.Mock(return_value={"tenant_id": "acme"})
                    ))
                )),
                __exit__=mock.MagicMock(return_value=False),
            ),
        ):
            row = provisioning.get_tenant_stack(_owner(), "acme")
        self.assertEqual(row["tenant_id"], "acme")


if __name__ == "__main__":
    unittest.main()
