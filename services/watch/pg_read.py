"""PostgreSQL read adapter for watch (read-only phase)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from services.db.pg_pool import main_read_connection


def enabled() -> bool:
    return os.environ.get("SCIPAL_WATCH_BACKEND", "").strip().lower() in {
        "postgres", "postgresql", "pg", "1", "true"
    }


def list_profiles(owner: Optional[str] = None) -> List[Dict]:
    pg = main_read_connection()
    try:
        if owner:
            rows = pg.execute(
                "SELECT * FROM watch_profiles WHERE owner = %s ORDER BY id", (owner,)
            ).fetchall()
        else:
            rows = pg.execute("SELECT * FROM watch_profiles ORDER BY id").fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def get_profile(profile_id: int, owner: Optional[str] = None) -> Optional[Dict]:
    pg = main_read_connection()
    try:
        row = pg.execute(
            "SELECT * FROM watch_profiles WHERE id = %s", (profile_id,)
        ).fetchone()
        if row and owner and (row["owner"] or "default") != owner:
            return None
        return dict(row) if row else None
    finally:
        pg.close()


def list_runs(profile_id: int, limit: int = 20) -> List[Dict]:
    pg = main_read_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM watch_runs WHERE profile_id = %s ORDER BY id DESC LIMIT %s",
            (profile_id, max(1, limit)),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def get_run(run_id: int) -> Optional[Dict]:
    pg = main_read_connection()
    try:
        row = pg.execute("SELECT * FROM watch_runs WHERE id = %s", (run_id,)).fetchone()
        return dict(row) if row else None
    finally:
        pg.close()


def list_items(run_id: int) -> List[Dict]:
    pg = main_read_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM watch_items WHERE run_id = %s ORDER BY id", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
