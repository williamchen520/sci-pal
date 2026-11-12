#!/usr/bin/env python3
"""Deterministic preflight gate for high-risk changes.

This is intentionally outside the Flask app. It classifies a change manifest
(paths + operations + optional line count) against config/governance_gates.json
and exits non-zero when human approval is required.

It is not a kernel sandbox: the gate is only as strong as the workflow that
runs it before edits/commands. The approval itself remains a human act.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config" / "governance_gates.json"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_matches(path: str, prefixes: list[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in prefixes)


def check(
    *,
    paths: list[str] | None = None,
    ops: list[str] | None = None,
    lines: int = 0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or load_config()
    paths = [path for path in (paths or []) if path]
    ops = set(ops or [])
    hits = []
    for trigger in cfg.get("triggers", []):
        path_hit = _path_matches_any(paths, trigger.get("paths") or [])
        op_hit = bool(ops & set(trigger.get("ops") or []))
        line_hit = bool(trigger.get("max_lines")) and lines > int(trigger["max_lines"])
        if path_hit or op_hit or line_hit:
            hits.append(
                {
                    "id": trigger["id"],
                    "name": trigger["name"],
                    "reason": trigger.get("reason", ""),
                    "path_hit": path_hit,
                    "op_hit": op_hit,
                    "line_hit": line_hit,
                }
            )
    return {
        "blocked": bool(hits),
        "approval_required": bool(hits),
        "triggers": hits,
        "paths": paths,
        "ops": sorted(ops),
        "lines": lines,
    }


def _path_matches_any(paths: list[str], prefixes: list[str]) -> bool:
    return any(_path_matches(path, prefixes) for path in paths)


def format_block(result: dict[str, Any], *, plan: str, risk: str) -> str:
    names = "、".join(f"[{hit['name']}]" for hit in result.get("triggers", []))
    reasons = "；".join(hit.get("reason", "") for hit in result.get("triggers", []))
    return (
        f"⚠️【拦截警告】当前任务触发了 {names} 规则。\n"
        f"📝【计划简述】{plan or '（未提供）'}\n"
        f"⚠️【风险提示】{risk or reasons or '（未提供）'}\n"
        "⏳ 请人类审查并回复“批准执行”以继续。"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", nargs="*", default=[], help="changed paths")
    parser.add_argument("--ops", nargs="*", default=[], help="operation tags")
    parser.add_argument("--lines", type=int, default=0, help="estimated changed lines")
    parser.add_argument("--plan", default="", help="short plan for the warning")
    parser.add_argument("--risk", default="", help="risk note for the warning")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)

    result = check(
        paths=args.paths,
        ops=args.ops,
        lines=args.lines,
        config=load_config(Path(args.config)),
    )
    result["plan"] = args.plan
    result["risk"] = args.risk

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["blocked"]:
        print(format_block(result, plan=args.plan, risk=args.risk))
    else:
        print("GOVERNANCE_GATE_OK")
    return 2 if result["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
