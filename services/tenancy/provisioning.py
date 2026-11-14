"""Tenant-stack planning and registration.

The application process records a plan and creates its storage prefix.  It does
not hold superuser DDL credentials; database creation is performed by the admin
CLI in ``scripts/provision_tenant.py``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from services.db.pg_pool import core_connection
from services.tenancy.capabilities import Principal, require_capability

TENANT_RE = re.compile(r"^[a-z][a-z0-9-]{2,40}$")


class ProvisioningError(ValueError):
    """Invalid tenant provisioning request."""


def _validate_tenant(tenant_id: str) -> str:
    value = (tenant_id or "").strip().lower()
    if not TENANT_RE.fullmatch(value):
        raise ProvisioningError(
            "tenant_id must be 3-41 chars: lowercase letter, digits, hyphen"
        )
    return value


def storage_root() -> Path:
    raw = os.environ.get("SCIPAL_TENANT_STORAGE_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path(__file__).resolve().parents[2] / "data" / "tenants").resolve()


def stack_plan(tenant_id: str) -> dict[str, Any]:
    slug = _validate_tenant(tenant_id)
    database_name = f"scipal_tenant_{slug}"
    if len(database_name) > 63:
        raise ProvisioningError("database name exceeds 63 characters")
    return {
        "tenant_id": slug,
        "slug": slug,
        "database_name": database_name,
        "storage_prefix": f"data/tenants/{slug}",
        "storage_path": str(storage_root() / slug),
        "index_prefix": f"tenant:{slug}:",
        "code_schema": "code",
    }


def _upsert_stack(plan: dict[str, Any]) -> dict[str, Any]:
    with core_connection() as pg:
        row = pg.execute(
            """
            INSERT INTO tenant_stacks
              (tenant_id, slug, database_name, storage_prefix, index_prefix,
               code_schema, status)
            VALUES (%s,%s,%s,%s,%s,%s,'planned')
            ON CONFLICT (tenant_id) DO UPDATE SET
              slug=EXCLUDED.slug,
              database_name=EXCLUDED.database_name,
              storage_prefix=EXCLUDED.storage_prefix,
              index_prefix=EXCLUDED.index_prefix,
              code_schema=EXCLUDED.code_schema,
              status=CASE
                WHEN tenant_stacks.status='provisioned' THEN 'provisioned'
                ELSE 'planned'
              END,
              updated_at=now()
            RETURNING tenant_id,slug,database_name,storage_prefix,index_prefix,
                      code_schema,status,created_at,updated_at
            """,
            (
                plan["tenant_id"],
                plan["slug"],
                plan["database_name"],
                plan["storage_prefix"],
                plan["index_prefix"],
                plan["code_schema"],
            ),
        ).fetchone()
    return dict(row)


def provision_tenant(principal: Principal, tenant_id: str) -> dict[str, Any]:
    require_capability(principal, "platform.tenant.manage", "platform")
    plan = stack_plan(tenant_id)
    Path(plan["storage_path"]).mkdir(parents=True, exist_ok=True)
    row = _upsert_stack(plan)
    row["storage_path"] = plan["storage_path"]
    return row


def mark_provisioned(tenant_id: str) -> dict[str, Any]:
    slug = _validate_tenant(tenant_id)
    with core_connection() as pg:
        row = pg.execute(
            "UPDATE tenant_stacks SET status='provisioned', updated_at=now() "
            "WHERE tenant_id=%s RETURNING tenant_id,status",
            (slug,),
        ).fetchone()
    if not row:
        raise ProvisioningError(f"tenant not found: {slug}")
    return dict(row)


def get_tenant_stack(principal: Principal, tenant_id: str) -> dict[str, Any] | None:
    slug = _validate_tenant(tenant_id)
    if principal.platform_role != "platform_owner":
        require_capability(principal, "tenant.read", f"tenant:{slug}")
    with core_connection() as pg:
        row = pg.execute(
            "SELECT tenant_id,slug,database_name,storage_prefix,index_prefix,"
            "code_schema,status,created_at,updated_at FROM tenant_stacks WHERE tenant_id=%s",
            (slug,),
        ).fetchone()
    return dict(row) if row else None
