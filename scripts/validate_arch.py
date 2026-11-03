#!/usr/bin/env python3
"""Validate Flask routes and handler signatures against ARCHITECTURE.json.

This is the guardrail behind "architecture as code":

1. every implemented route must exist in the JSON;
2. every JSON route must exist in Flask unless it is marked ``planned``;
3. route methods must match;
4. path variables and declared parameters must be accepted by the handler.

Run after editing ARCHITECTURE.json and before/after changing Python routes.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PATH_PARAM = re.compile(r"<(?:(?:[^:<>]+):)?([^<>]+)>")
IGNORED_METHODS = {"HEAD", "OPTIONS"}


def route_key(rule: str, method: str) -> tuple[str, str]:
    return rule, method.upper()


def methods_of(endpoint: dict[str, Any]) -> set[str]:
    return {m.upper() for m in endpoint.get("methods") or ["GET"]} - IGNORED_METHODS


def path_params(rule: str) -> set[str]:
    return set(PATH_PARAM.findall(rule))


def _accepts(func: Any, name: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return True
    if name in signature.parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values())


def load_architecture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    endpoints = data.get("api", {}).get("endpoints")
    if not isinstance(endpoints, list):
        raise ValueError("ARCHITECTURE.json: api.endpoints must be a list")
    return data


def validate(arch: dict[str, Any], app: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    json_keys: dict[tuple[str, str], dict[str, Any]] = {}
    for endpoint in arch.get("api", {}).get("endpoints", []):
        rule = endpoint.get("rule")
        if not rule:
            errors.append("endpoint without rule")
            continue
        if endpoint.get("status") == "planned":
            continue
        for method in methods_of(endpoint):
            key = route_key(rule, method)
            if key in json_keys:
                errors.append(f"duplicate endpoint in JSON: {method} {rule}")
            json_keys[key] = endpoint

    app_keys: dict[tuple[str, str], Any] = {}
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        for method in rule.methods - IGNORED_METHODS:
            app_keys[route_key(rule.rule, method)] = rule

    for key in sorted(app_keys.keys() - json_keys.keys()):
        errors.append(f"wild route not in ARCHITECTURE.json: {key[1]} {key[0]}")
    for key in sorted(json_keys.keys() - app_keys.keys()):
        errors.append(f"documented route missing from Flask: {key[1]} {key[0]}")

    for key, endpoint in json_keys.items():
        func = app.view_functions.get(endpoint.get("endpoint") or "")
        if func is None:
            errors.append(f"handler not found: {endpoint.get('endpoint')} for {key[1]} {key[0]}")
            continue
        for param in path_params(key[0]):
            if not _accepts(func, param):
                errors.append(
                    f"handler {endpoint.get('endpoint')} does not accept path param '{param}'"
                )
        for param in endpoint.get("parameters") or []:
            name = param if isinstance(param, str) else param.get("name")
            if name and not _accepts(func, name):
                errors.append(
                    f"handler {endpoint.get('endpoint')} does not accept parameter '{name}'"
                )

    if not errors:
        for endpoint in arch.get("api", {}).get("endpoints", []):
            if endpoint.get("status") == "planned":
                warnings.append(f"planned endpoint not implemented: {endpoint.get('rule')}")

    return {
        "ok": not errors,
        "json_routes": len(json_keys),
        "app_routes": len(app_keys),
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", default=str(ROOT / "ARCHITECTURE.json"))
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    args = parser.parse_args()

    arch = load_architecture(Path(args.arch))
    import api_server  # noqa: E402

    result = validate(arch, api_server.app)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"json_routes={result['json_routes']} app_routes={result['app_routes']}")
        for item in result["errors"]:
            print(f"ERROR {item}")
        for item in result["warnings"]:
            print(f"WARN  {item}")
        print("OK" if result["ok"] else "FAILED")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
