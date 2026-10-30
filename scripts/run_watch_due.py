"""Run due watch profiles once or in a loop.

Examples:
  python scripts/run_watch_due.py --once
  python scripts/run_watch_due.py --loop --interval 300
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_db.watch_schema import migrate
from services.watch import scheduler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/research.db")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    migrate(args.db)
    if not args.loop:
        results = scheduler.run_due(args.db, limit=args.limit)
        for result in results:
            print(result)
        return 0 if all(item.get("ok") for item in results) else 1
    print(f"watch scheduler started; interval={args.interval}s", flush=True)
    while True:
        try:
            results = scheduler.run_due(args.db, limit=args.limit)
            for result in results:
                print(result, flush=True)
        except Exception as exc:  # noqa: BLE001 - keep loop alive
            print(f"scheduler error: {exc}", file=sys.stderr, flush=True)
        time.sleep(max(args.interval, 30))


if __name__ == "__main__":
    raise SystemExit(main())
