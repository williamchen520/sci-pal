"""Due-profile scheduler for watch runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.watch import pg_store, runner


def due_profiles(
    conn,
    now: Optional[datetime] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat()
    if pg_store.enabled():
        from services.db.pg_pool import pg_connection

        pg = pg_connection()
        try:
            rows = pg.execute(
                "SELECT * FROM watch_profiles "
                "WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= %s) "
                "ORDER BY COALESCE(next_run_at, '') ASC, id ASC LIMIT %s",
                (stamp, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            pg.close()
    rows = conn.execute(
        "SELECT * FROM watch_profiles "
        "WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?) "
        "ORDER BY COALESCE(next_run_at, '') ASC, id ASC LIMIT ?",
        (stamp, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def run_due(
    db_path: Path | str,
    now: Optional[datetime] = None,
    limit: int = 20,
    run_profile=None,
    profiles=None,
) -> List[Dict[str, Any]]:
    """Run every due profile once; failures do not stop the batch."""
    if profiles is None:
        profiles = due_profiles(None, now=now, limit=limit)
    runner_fn = run_profile or runner.run_profile
    results: List[Dict[str, Any]] = []
    for profile in profiles:
        try:
            result = runner_fn(db_path, profile["id"])
            results.append({"profile_id": profile["id"], "ok": True, **result})
        except Exception as exc:  # noqa: BLE001 - batch must continue
            results.append(
                {"profile_id": profile["id"], "ok": False, "error": str(exc)[:500]}
            )
    return results
