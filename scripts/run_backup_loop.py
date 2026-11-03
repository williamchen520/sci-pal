#!/usr/bin/env python3
"""Run verified SciPal backups on a fixed interval with retention."""

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


def prune(out: Path, retention_days: int) -> list[str]:
    if retention_days <= 0:
        return []
    cutoff = time.time() - retention_days * 86400
    removed = []
    for archive in sorted(out.glob("scipal-*.tar.gz")):
        if archive.stat().st_mtime < cutoff:
            archive.unlink()
            removed.append(archive.name)
    return removed


def run_once(data: Path, out: Path, *, retention_days: int, expected_papers: int | None) -> dict:
    archive = create_archive(data, out)
    result = verify_archive(archive, expected_papers=expected_papers)
    result["pruned"] = prune(out, retention_days)
    result["created_at"] = datetime.now(timezone.utc).isoformat()
    status = out / "backup_status.json"
    status.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/app/data")
    parser.add_argument("--out", default="/app/backups")
    parser.add_argument("--interval-hours", type=float, default=24.0)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--expected-papers", type=int, default=None)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    data = Path(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            result = run_once(
                data,
                out,
                retention_days=args.retention_days,
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
