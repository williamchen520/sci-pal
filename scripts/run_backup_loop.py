#!/usr/bin/env python3
"""Daily DB backups + weekly full backups, with verification and retention."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deploy.backup import create_archive  # noqa: E402
from scripts.verify_backup import verify_archive  # noqa: E402

STATE_FILE = "backup_state.json"


def _load_state(out: Path) -> dict:
    path = out / STATE_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(out: Path, state: dict) -> None:
    (out / STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _age_days(timestamp: str | None) -> float:
    if not timestamp:
        return 10**9
    try:
        then = datetime.fromisoformat(timestamp)
    except ValueError:
        return 10**9
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400


def choose_scope(out: Path, full_interval_days: int) -> str:
    state = _load_state(out)
    return "full" if _age_days(state.get("last_full_at")) >= full_interval_days else "db"


def prune(out: Path, scope: str, retention_days: int) -> list[str]:
    if retention_days <= 0:
        return []
    cutoff = time.time() - retention_days * 86400
    removed = []
    for archive in sorted(out.glob(f"scipal-{scope}-*.tar.gz")):
        if archive.stat().st_mtime < cutoff:
            archive.unlink()
            removed.append(archive.name)
    return removed


def run_once(
    data: Path,
    out: Path,
    *,
    scope: str,
    db_retention_days: int,
    full_retention_days: int,
    expected_papers: int | None,
) -> dict:
    archive = create_archive(data, out, scope=scope)
    result = verify_archive(archive, expected_papers=expected_papers)
    result["scope"] = scope
    retention = db_retention_days if scope == "db" else full_retention_days
    result["pruned"] = prune(out, scope, retention)
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    state = _load_state(out)
    state[f"last_{scope}_at"] = result["created_at"]
    state["last_scope"] = scope
    _save_state(out, state)
    (out / "backup_status.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/app/data")
    parser.add_argument("--out", default="/app/backups")
    parser.add_argument("--interval-hours", type=float, default=24.0)
    parser.add_argument("--db-retention-days", type=int, default=30)
    parser.add_argument("--full-retention-days", type=int, default=28)
    parser.add_argument("--full-interval-days", type=int, default=7)
    parser.add_argument("--force-scope", choices=("db", "full"), default="")
    parser.add_argument("--expected-papers", type=int, default=None)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    data = Path(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            scope = args.force_scope or choose_scope(out, args.full_interval_days)
            result = run_once(
                data,
                out,
                scope=scope,
                db_retention_days=args.db_retention_days,
                full_retention_days=args.full_retention_days,
                expected_papers=args.expected_papers,
            )
            if not result["ok"]:
                raise RuntimeError(f"backup verification failed: {result}")
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:  # noqa: BLE001
            failure = {
                "ok": False,
                "error": str(exc)[:500],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            (out / "backup_status.json").write_text(
                json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(failure, ensure_ascii=False), flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(max(args.interval_hours, 1 / 60) * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
