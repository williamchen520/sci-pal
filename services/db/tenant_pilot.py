"""P4b2b1 tenant-pilot search path switch."""

from __future__ import annotations

import os

TABLES = {"reviews", "notes"}


def enabled_tables() -> set[str]:
    raw = os.environ.get("SCIPAL_TENANT_PILOT", "")
    return {part.strip().lower() for part in raw.split(",") if part.strip()} & TABLES


def set_search_path(pg, table: str) -> None:
    """Route one service to its tenant copy when the pilot is enabled."""
    if table in enabled_tables():
        pg.execute("SET search_path TO lib_ws_default, public")
    else:
        pg.execute("SET search_path TO public")
