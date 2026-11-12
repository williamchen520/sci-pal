#!/usr/bin/env python3
"""CI wrapper for the governance gate.

Runs from the base branch checkout, so a PR cannot weaken the gate script or
config it is being judged by. Changed paths come from the PR diff; the
``governance-approved`` label is the only bypass.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.governance_gate import check, format_block  # noqa: E402

APPROVAL_LABEL = "governance-approved"


def changed_paths(base: str, head: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=ROOT,
        text=True,
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def approved(labels: str) -> bool:
    return APPROVAL_LABEL in {part.strip() for part in labels.split(",") if part.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--plan", default="")
    parser.add_argument("--risk", default="")
    args = parser.parse_args(argv)

    paths = changed_paths(args.base, args.head)
    ops = [part for part in os.environ.get("GOVERNANCE_OPS", "").split(",") if part]
    labels = os.environ.get("GOVERNANCE_LABELS", "")
    result = check(paths=paths, ops=ops)

    print(f"changed_paths={len(paths)}")
    for path in paths:
        print(f"  {path}")

    if result["blocked"] and not approved(labels):
        print(format_block(result, plan=args.plan, risk=args.risk))
        print(f"add label {APPROVAL_LABEL!r} after human approval")
        return 2

    if result["blocked"]:
        print(f"GOVERNANCE_CI_APPROVED label={APPROVAL_LABEL}")
    else:
        print("GOVERNANCE_CI_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
