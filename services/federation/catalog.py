"""Star-topology federation catalog.

The catalog stores metadata only.  It intentionally has no tenant-to-tenant
target: the database CHECK constraints and this service both reject it.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterable

from services.db.pg_pool import core_connection
from services.tenancy.capabilities import (
    AccessDenied,
    FEDERATION_SCOPES,
    Principal,
    allowed_federation_scopes,
    can,
    require_capability,
)


class FederationError(ValueError):
    """Invalid federation operation."""


def assert_star_target(target_kind: str, target_tenant_id: str | None = None) -> None:
    if target_kind != "main":
        raise FederationError("federation target must be main")
    if target_tenant_id:
        raise FederationError("tenant-to-tenant federation is forbidden")


def _normalize_scopes(scopes: Iterable[str]) -> list[str]:
    values = sorted({str(scope).strip().lower() for scope in scopes if str(scope).strip()})
    if not values:
        values = ["own"]
    if not set(values) <= FEDERATION_SCOPES:
        raise FederationError(f"invalid federation scopes: {values}")
    return values


def _upsert_link(
    *,
    tenant_id: str,
    library_id: str,
    source_kind: str,
    allowed_scopes: list[str],
    db_ref: str,
    index_name: str,
) -> dict[str, Any]:
    catalog_id = "fed_" + uuid.uuid4().hex[:16]
    with core_connection() as pg:
        row = pg.execute(
            """
            INSERT INTO federation_catalog
              (catalog_id, tenant_id, library_id, source_kind,
               target_kind, target_tenant_id, allowed_scopes, db_ref, index_name, status)
            VALUES (%s,%s,%s,%s,'main',NULL,%s,%s,%s,'active')
            ON CONFLICT (tenant_id, library_id) DO UPDATE SET
              source_kind=EXCLUDED.source_kind,
              target_kind='main',
              target_tenant_id=NULL,
              allowed_scopes=EXCLUDED.allowed_scopes,
              db_ref=EXCLUDED.db_ref,
              index_name=EXCLUDED.index_name,
              status='active'
            RETURNING catalog_id,tenant_id,library_id,source_kind,target_kind,
                      target_tenant_id,allowed_scopes,db_ref,index_name,status,created_at
            """,
            (
                catalog_id,
                tenant_id,
                library_id,
                source_kind,
                allowed_scopes,
                db_ref,
                index_name,
            ),
        ).fetchone()
    return dict(row)


def _fetch_link(tenant_id: str, library_id: str = "") -> dict[str, Any] | None:
    with core_connection() as pg:
        if library_id:
            row = pg.execute(
                "SELECT * FROM federation_catalog "
                "WHERE tenant_id=%s AND library_id=%s AND status='active'",
                (tenant_id, library_id),
            ).fetchone()
        else:
            row = pg.execute(
                "SELECT * FROM federation_catalog "
                "WHERE tenant_id=%s AND status='active' ORDER BY library_id LIMIT 1",
                (tenant_id,),
            ).fetchone()
    return dict(row) if row else None


def _query_links(tenant_id: str) -> list[dict[str, Any]]:
    with core_connection() as pg:
        rows = pg.execute(
            "SELECT * FROM federation_catalog WHERE tenant_id=%s ORDER BY library_id",
            (tenant_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def register_main_link(
    principal: Principal,
    *,
    tenant_id: str,
    library_id: str,
    allowed_scopes: Iterable[str],
    source_kind: str = "paper",
    db_ref: str = "",
    index_name: str = "",
) -> dict[str, Any]:
    require_capability(principal, "platform.federation.manage", "platform")
    if not tenant_id or not library_id:
        raise FederationError("tenant_id and library_id are required")
    assert_star_target("main", None)
    scopes = _normalize_scopes(allowed_scopes)
    return _upsert_link(
        tenant_id=tenant_id,
        library_id=library_id,
        source_kind=source_kind,
        allowed_scopes=scopes,
        db_ref=db_ref,
        index_name=index_name,
    )


def list_links(principal: Principal, tenant_id: str) -> list[dict[str, Any]]:
    require_capability(principal, "tenant.read", f"tenant:{tenant_id}")
    return _query_links(tenant_id)


def resolve_catalog_scope(
    principal: Principal, tenant_id: str, requested: str = "own"
) -> str:
    if tenant_id not in principal.memberships:
        raise AccessDenied("tenant membership required")
    value = (requested or "own").strip().lower()
    if value not in FEDERATION_SCOPES:
        raise AccessDenied(f"federation scope is not allowed: {requested!r}")

    allowed = {"own"}
    link = _fetch_link(tenant_id)
    if link:
        allowed |= set(link.get("allowed_scopes") or [])
    allowed &= set(allowed_federation_scopes(principal, tenant_id))

    if value not in allowed:
        raise AccessDenied(f"federation scope requires catalog link: {value}")
    return value
