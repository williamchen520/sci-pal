#!/usr/bin/env python3
"""U1: single import worker for queued ImportSessions."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.imports.queue import run_once  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--import-id", default="")
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    while True:
        result = run_once(args.import_id or None)
        if result:
            print(json.dumps(result, ensure_ascii=False, default=str)[:2000], flush=True)
        if args.once:
            return 0 if result is not None else 3
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
