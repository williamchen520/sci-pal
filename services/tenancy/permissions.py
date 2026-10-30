"""Cross-resource access rules for PI oversight."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config.settings import DATABASE_PATH

READABLE_BY_PI = {"public", "internal"}


def pi_can_read(data_class: str) -> bool:
    return (data_class or "internal").lower() in READABLE_BY_PI


def pi_can_copy(data_class: str) -> bool:
    return pi_can_read(data_class)


def audit(
    workspace_id: str,
    actor_user_id: str,
    action: str,
    *,
    target: str | None = None,
    detail: str | None = None,
    db_path: str | Path = DATABASE_PATH,
) -> None:
    path = Path(db_path)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO tenancy_audit (workspace_id, actor_user_id, action, target, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (workspace_id, actor_user_id, action, target, detail),
        )
        conn.commit()
    finally:
        conn.close()
