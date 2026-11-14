#!/usr/bin/env python3
"""Plan or execute a tenant database/schema stack.

The app process never gets the superuser DSN.  Run this CLI with
SCIPAL_PG_PROVISION_DSN pointing at an admin role that may CREATE DATABASE.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.tenancy.capabilities import Principal
from services.tenancy.provisioning import (
    mark_provisioned,
    provision_tenant,
    stack_plan,
)


def _create_database(dsn: str, plan: dict) -> None:
    with psycopg.connect(dsn, autocommit=True) as admin:
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (plan["database_name"],)
        ).fetchone()
        if not exists:
            admin.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(plan["database_name"])
                )
            )
    with psycopg.connect(dsn, dbname=plan["database_name"], autocommit=True) as tenant:
        for schema in ("xml", "html", "pdf", plan["code_schema"]):
            tenant.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_PG_PROVISION_DSN", ""))
    args = parser.parse_args()

    principal = Principal(user_id="cli", platform_role="platform_owner")
    row = provision_tenant(principal, args.tenant_id)
    plan = stack_plan(args.tenant_id)
    if not args.execute:
        print(f"TENANT_PLANNED tenant={plan['tenant_id']} db={plan['database_name']} storage={plan['storage_path']}")
        print(
            "DDL: CREATE DATABASE "
            f"{plan['database_name']}; schemas xml/html/pdf/{plan['code_schema']}"
        )
        return 0

    if not args.dsn:
        raise SystemExit("SCIPAL_PG_PROVISION_DSN or --dsn is required for --execute")
    _create_database(args.dsn, plan)
    mark_provisioned(plan["tenant_id"])
    print(
        f"TENANT_PROVISIONED tenant={plan['tenant_id']} db={plan['database_name']} "
        f"storage={plan['storage_path']} status={row['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
