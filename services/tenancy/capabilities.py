"""Capability and resource-scope authorization.

This module is the E0 foundation for tenant isolation.  It deliberately does
not touch the legacy ``authorize()`` path; new entry points should use ``can``
and ``require_capability``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

CAPABILITIES = frozenset(
    {
        "platform.tenant.manage",
        "platform.plugin.manage",
        "platform.federation.manage",
        "tenant.read",
        "tenant.import",
        "tenant.review",
        "tenant.publish",
        "tenant.members.manage",
        "tenant.plugin.enable",
        "library.read",
        "library.write",
        "library.index",
    }
)

PLATFORM_CAPABILITIES = frozenset(c for c in CAPABILITIES if c.startswith("platform."))
TENANT_CAPABILITIES = frozenset(c for c in CAPABILITIES if c.startswith("tenant."))
LIBRARY_CAPABILITIES = frozenset(c for c in CAPABILITIES if c.startswith("library."))

ROLE_CAPABILITIES = {
    "platform_owner": PLATFORM_CAPABILITIES,
    "tenant_owner": TENANT_CAPABILITIES | LIBRARY_CAPABILITIES,
    "tenant_admin": TENANT_CAPABILITIES | LIBRARY_CAPABILITIES,
    "tenant_reviewer": frozenset({"tenant.read", "tenant.review", "library.read"}),
    "tenant_member": frozenset(
        {"tenant.read", "tenant.import", "library.read", "library.write"}
    ),
    "tenant_viewer": frozenset({"tenant.read", "library.read"}),
}

LEGACY_ROLE_MAP = {
    "owner": "tenant_owner",
    "pi": "tenant_admin",
    "member": "tenant_member",
    "reviewer": "tenant_reviewer",
    "viewer": "tenant_viewer",
}

FEDERATION_SCOPES = frozenset({"own", "main", "both"})


class AccessDenied(PermissionError):
    """The principal is not allowed to perform the capability."""


@dataclass(frozen=True)
class ResourceScope:
    kind: str
    id: str = ""

    @classmethod
    def parse(cls, value: str) -> "ResourceScope":
        raw = (value or "").strip()
        if raw == "platform":
            return cls("platform")
        if raw.startswith("tenant:") and raw[7:]:
            return cls("tenant", raw[7:])
        if raw.startswith("library:") and raw[8:]:
            return cls("library", raw[8:])
        raise ValueError(f"invalid resource scope: {value!r}")


@dataclass(frozen=True)
class Principal:
    user_id: str
    platform_role: str | None = None
    memberships: Mapping[str, str] = field(default_factory=dict)
    library_tenants: Mapping[str, str] = field(default_factory=dict)
    main_subscribed: bool = False


def normalize_role(role: str) -> str:
    value = (role or "").strip()
    return LEGACY_ROLE_MAP.get(value, value)


def _role_for(principal: Principal, tenant_id: str) -> str:
    return normalize_role(principal.memberships.get(tenant_id, ""))


def _allowed_capabilities(principal: Principal, tenant_id: str) -> frozenset[str]:
    return ROLE_CAPABILITIES.get(_role_for(principal, tenant_id), frozenset())


def can(principal: Principal, capability: str, scope: str | ResourceScope) -> bool:
    if capability not in CAPABILITIES:
        return False
    parsed = ResourceScope.parse(scope) if isinstance(scope, str) else scope

    if parsed.kind == "platform":
        return (
            principal.platform_role == "platform_owner"
            and capability in PLATFORM_CAPABILITIES
        )

    if parsed.kind == "tenant":
        if parsed.id not in principal.memberships:
            return False
        allowed = _allowed_capabilities(principal, parsed.id)
        return capability in allowed and not capability.startswith("platform.")

    if parsed.kind == "library":
        tenant_id = principal.library_tenants.get(parsed.id)
        if not tenant_id or tenant_id not in principal.memberships:
            return False
        allowed = _allowed_capabilities(principal, tenant_id)
        return capability in LIBRARY_CAPABILITIES and capability in allowed

    return False


def require_capability(
    principal: Principal, capability: str, scope: str | ResourceScope
) -> None:
    if not can(principal, capability, scope):
        raise AccessDenied(f"{capability} denied on {scope}")


def allowed_federation_scopes(principal: Principal, tenant_id: str) -> list[str]:
    """Return only own/main/both; never another tenant."""
    if tenant_id not in principal.memberships:
        return []
    scopes = ["own"]
    if principal.main_subscribed:
        scopes.append("main")
        scopes.append("both")
    return scopes


def resolve_federation_scope(
    principal: Principal, tenant_id: str, requested: str
) -> list[str]:
    """Validate a requested scope against the star topology."""
    allowed = set(allowed_federation_scopes(principal, tenant_id))
    value = (requested or "own").strip().lower()
    if value not in FEDERATION_SCOPES:
        raise AccessDenied(f"federation scope is not allowed: {requested!r}")
    if value not in allowed:
        raise AccessDenied(f"federation scope requires subscription: {value}")
    return [value]
