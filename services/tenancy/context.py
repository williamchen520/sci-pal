"""Tenant-ready execution context.

S0 delivers one tenant plus main.  The context centralizes resource resolution
so new code does not read global ``SCIPAL_PG_*`` values directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TENANT_ID = "default"
TRUE_VALUES = {"1", "true", "yes", "on"}


class TenantContextError(ValueError):
    """Tenant context is missing or invalid."""


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    database_dsn_ref: str
    storage_root: str
    index_prefix: str
    main_federation_enabled: bool
    source_schemas: tuple[str, ...] = ("xml", "html", "pdf")
    code_schema: str = "code"

    @property
    def scope(self) -> str:
        return f"tenant:{self.tenant_id}"

    @property
    def storage_path(self) -> Path:
        return Path(self.storage_root)

    def resolve_dsn(self, name: str = "corpus") -> str:
        refs = {
            "corpus": (self.database_dsn_ref, "SCIPAL_PG_CORPUS_DSN"),
            "core": ("SCIPAL_TENANT_CORE_DSN", "SCIPAL_CORE_DSN", "SCIPAL_PG_DSN"),
            "code": ("SCIPAL_TENANT_CODE_DSN", "SCIPAL_CODE_READ_DSN"),
        }
        if name not in refs:
            raise TenantContextError(f"unknown connection: {name}")
        for ref in refs[name]:
            value = os.environ.get(ref, "").strip()
            if value:
                return value
        raise TenantContextError(f"no DSN configured for {name}")

    def connection(self, name: str = "corpus"):
        from services.db.pg_pool import pg_connection

        return pg_connection(self.resolve_dsn(name))

    def allows_federation_scope(self, requested: str) -> bool:
        value = (requested or "own").strip().lower()
        if value == "own":
            return True
        if value in {"main", "both"}:
            return self.main_federation_enabled
        return False

    def public_dict(self) -> dict[str, Any]:
        """Metadata safe to expose; never includes DSN values."""
        return {
            "tenant_id": self.tenant_id,
            "scope": self.scope,
            "database_dsn_ref": self.database_dsn_ref,
            "storage_root": self.storage_root,
            "index_prefix": self.index_prefix,
            "main_federation_enabled": self.main_federation_enabled,
            "source_schemas": list(self.source_schemas),
            "code_schema": self.code_schema,
        }


def context_from_env(tenant_id: str | None = None) -> TenantContext:
    resolved_tenant = (tenant_id or os.environ.get("SCIPAL_TENANT_ID") or DEFAULT_TENANT_ID).strip()
    if not resolved_tenant:
        raise TenantContextError("tenant_id is empty")
    root = os.environ.get("SCIPAL_TENANT_STORAGE_ROOT", "").strip()
    if not root:
        root = str((Path(__file__).resolve().parents[2] / "data" / "tenants" / resolved_tenant).resolve())
    main_enabled = os.environ.get("SCIPAL_TENANT_MAIN_FEDERATION", "1").strip().lower() in TRUE_VALUES
    return TenantContext(
        tenant_id=resolved_tenant,
        database_dsn_ref=os.environ.get(
            "SCIPAL_TENANT_DB_DSN_REF", "SCIPAL_TENANT_DB_DSN"
        ).strip()
        or "SCIPAL_TENANT_DB_DSN",
        storage_root=root,
        index_prefix=os.environ.get(
            "SCIPAL_TENANT_INDEX_PREFIX", f"tenant:{resolved_tenant}:"
        ).strip()
        or f"tenant:{resolved_tenant}:",
        main_federation_enabled=main_enabled,
    )


def current_context() -> TenantContext:
    return context_from_env()
