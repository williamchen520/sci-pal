#!/usr/bin/env python3
"""Separated PostgreSQL backups for scipal_core and scipal_rebuild.

Policy:
  core    every 6h, retention 7d  (identity/business, high value)
  corpus  every 7d, retention 28d (rebuildable from XML)

Requires pg_dump/pg_restore in the runtime image.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

STATE = "pg_backup_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(out: Path) -> dict:
    path = out / STATE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(out: Path, state: dict) -> None:
    (out / STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _age_hours(timestamp: str | None) -> float:
    if not timestamp:
        return 10**9
    try:
        then = datetime.fromisoformat(timestamp)
    except ValueError:
        return 10**9
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def _dump(name: str, dsn: str, out: Path) -> Path:
    if not dsn:
        raise RuntimeError(f"{name} DSN is missing")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = out / f"{name}-{stamp}.dump"
    subprocess.run(
        ["pg_dump", dsn, "--format=custom", "--no-owner", "--no-acl", "--file", str(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    # Verify the archive is readable; a dump that cannot list is not a backup.
    subprocess.run(
        ["pg_restore", "--list", str(target)],
        check=True,
        capture_output=True,
        text=True,
    )
    return target


def _prune(out: Path, name: str, retention_days: int) -> list[str]:
    cutoff = time.time() - retention_days * 86400
    removed = []
    for path in sorted(out.glob(f"{name}-*.dump")):
        if path.stat().st_mtime < cutoff:
            path.unlink()
            removed.append(path.name)
    return removed


def run_once(out: Path, core_days: int, corpus_days: int, force: str = "") -> dict:
    out.mkdir(parents=True, exist_ok=True)
    state = _load(out)
    result = {"ok": True, "created_at": _now(), "items": []}
    jobs = []
    if force in {"", "core"}:
        jobs.append(("core", "SCIPAL_CORE_DSN", 6.0, core_days))
    if force in {"", "corpus"}:
        jobs.append(("corpus", "SCIPAL_PG_CORPUS_DSN", 24.0 * 7, corpus_days))
    for name, env, interval_hours, retention in jobs:
        if force == "" and _age_hours(state.get(f"last_{name}_at")) < interval_hours:
            continue
        try:
            target = _dump(name, os.environ.get(env, ""), out)
            removed = _prune(out, name, retention)
            state[f"last_{name}_at"] = _now()
            state[f"last_{name}_file"] = target.name
            result["items"].append({"name": name, "file": target.name, "bytes": target.stat().st_size, "pruned": removed})
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["items"].append({"name": name, "error": str(exc)[:300]})
    _save(out, state)
    (out / "pg_backup_status.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/app/backups/pg")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", choices=("", "core", "corpus"), default="")
    parser.add_argument("--core-retention-days", type=int, default=7)
    parser.add_argument("--corpus-retention-days", type=int, default=28)
    parser.add_argument("--interval-minutes", type=int, default=60)
    args = parser.parse_args()
    out = Path(args.out)
    while True:
        result = run_once(out, args.core_retention_days, args.corpus_retention_days, args.force)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.once:
            return 0 if result["ok"] else 1
        time.sleep(max(1, args.interval_minutes) * 60)


if __name__ == "__main__":
    raise SystemExit(main())
