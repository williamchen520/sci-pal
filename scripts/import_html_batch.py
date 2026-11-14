#!/usr/bin/env python3
"""H0: import a manifest of HTML files into one tenant library."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.imports.html_batch import (  # noqa: E402
    BatchError,
    load_manifest,
    run_batch,
    write_report,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", default="")
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()

    try:
        manifest = load_manifest(args.manifest)
        report = run_batch(manifest, limit=args.limit, dry_run=args.dry_run)
    except BatchError as exc:
        print(f"HTML_BATCH_ERROR {exc}")
        return 2

    if args.report:
        write_report(report, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2)[:2000])
    if args.fail_on_error and report["failed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
