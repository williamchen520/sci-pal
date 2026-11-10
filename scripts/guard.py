"""Architecture guard executor: read ARCH_CONTRACT.json, run rules.

Rules stay in JSON; this file only dispatches by ``kind``. Start with three
rules: route ownership, deadline TODOs, and new SQLite connections.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "ARCH_CONTRACT.json"
SKIP_PARTS = {".git", ".venv", "venv", "venv_sciPal_py312", "node_modules", "__pycache__"}


def load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def load_exceptions(contract: dict) -> dict[str, set[str]]:
    today = dt.date.today()
    out: dict[str, set[str]] = {}
    for item in contract.get("exceptions", []):
        if not item.get("expires"):
            raise SystemExit(f"guard: exception missing expires: {item}")
        if dt.date.fromisoformat(item["expires"]) < today:
            raise SystemExit(f"guard: exception expired: {item}")
        out.setdefault(item["rule"], set()).add(item["target"])
    return out


def git_new_files(staged: bool, base_ref: str) -> list[str]:
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=A"]
    elif base_ref:
        cmd = ["git", "diff", "--name-only", "--diff-filter=A", f"{base_ref}...HEAD"]
    else:
        return []
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def in_scope(path: Path, scope: str) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if "**" not in scope:
        return rel == scope
    prefix, suffix = scope.split("**", 1)
    prefix = prefix.rstrip("/")
    suffix = suffix.lstrip("*/")
    return rel.startswith(prefix + "/" if prefix else "") and rel.endswith(suffix)


def iter_files(scope: str):
    for path in ROOT.glob(scope):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        yield path


def check_route_unique(rule: dict, args) -> list[dict]:
    sys.path.insert(0, str(ROOT))
    import api_server  # noqa: E402

    owners: dict[tuple[str, str], set[str]] = {}
    for route in api_server.app.url_map.iter_rules():
        if route.endpoint == "static":
            continue
        blueprint = route.endpoint.split(".")[0] if "." in route.endpoint else "__app__"
        for method in route.methods - {"HEAD", "OPTIONS"}:
            owners.setdefault((str(route.rule), method), set()).add(blueprint)
    return [
        {
            "target": f"{method} {path}",
            "detail": f"registered by multiple blueprints: {sorted(bps)}",
        }
        for (path, method), bps in owners.items()
        if len(bps) > 1
    ]


def check_deadline(rule: dict, args) -> list[dict]:
    params = rule.get("params") or {}
    pattern = re.compile(params["pattern"])
    today = dt.date.today()
    violations = []
    for path in iter_files(params.get("scope", "**/*.py")):
        rel = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for match in pattern.finditer(line):
                deadline = dt.date.fromisoformat(match.group(1))
                if deadline < today:
                    violations.append(
                        {
                            "target": f"{rel}:{number}",
                            "detail": f"transition deadline expired: {match.group(0)}",
                        }
                    )
    return violations


def check_forbid_pattern(rule: dict, args) -> list[dict]:
    params = rule.get("params") or {}
    pattern = re.compile(params["pattern"])
    only_new = bool(params.get("only_new"))
    if only_new:
        files = [ROOT / name for name in git_new_files(args.staged, args.base_ref)]
    else:
        files = list(iter_files(params.get("scope", "**/*.py")))
    violations = []
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if not in_scope(path, params.get("scope", "**/*.py")):
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            violations.append(
                {"target": rel, "detail": f"forbidden pattern in new file: {params['pattern']}"}
            )
    return violations




def check_forbid_import(rule: dict, args) -> list[dict]:
    params = rule.get("params") or {}
    modules = tuple(params.get("modules") or ())
    names = set(params.get("names") or ())
    only_new = bool(params.get("only_new"))
    if only_new:
        files = [ROOT / name for name in git_new_files(args.staged, args.base_ref)]
    else:
        files = list(iter_files(params.get("scope", "**/*.py")))
    violations = []
    for path in files:
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if not in_scope(path, params.get("scope", "**/*.py")):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == module or alias.name.startswith(module + ".") for module in modules):
                        violations.append({"target": f"{rel}:{node.lineno}", "detail": f"forbidden import: {alias.name}"})
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                matched = any(module == forbidden or module.startswith(forbidden + ".") for forbidden in modules)
                if matched:
                    violations.append({"target": f"{rel}:{node.lineno}", "detail": f"forbidden import: {module}"})
                else:
                    for alias in node.names:
                        if alias.name in names:
                            violations.append({"target": f"{rel}:{node.lineno}", "detail": f"forbidden symbol: {alias.name}"})
    return violations

CHECKS = {
    "route_unique_blueprint": check_route_unique,
    "deadline_scan": check_deadline,
    "forbid_pattern": check_forbid_pattern,
    "forbid_import": check_forbid_import,
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--rule", default="", help="run a single rule id")
    parser.add_argument("--skip-rule", action="append", default=[], help="skip a rule id")
    args = parser.parse_args()

    contract = load_contract()
    exceptions = load_exceptions(contract)
    violations = []
    for rule in contract.get("rules", []):
        if args.rule and rule["id"] != args.rule:
            continue
        if rule["id"] in args.skip_rule:
            continue
        check = CHECKS.get(rule["kind"])
        if check is None:
            raise SystemExit(f"guard: unknown rule kind: {rule['kind']}")
        if rule.get("severity", "error") != "error":
            continue
        for item in check(rule, args):
            if item["target"] in exceptions.get(rule["id"], set()):
                continue
            item["rule"] = rule["id"]
            item["severity"] = rule.get("severity", "error")
            violations.append(item)

    if args.json:
        print(json.dumps({"ok": not violations, "violations": violations}, ensure_ascii=False, indent=2))
    else:
        for item in violations:
            print(f"ERROR [{item['rule']}] {item['target']}: {item['detail']}")
        print("GUARD_OK" if not violations else f"GUARD_FAILED {len(violations)}")
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
