#!/usr/bin/env python3
"""Generate Flask and MCP skeletons from an ARCHITECTURE.json node.

The JSON node must carry a ``codegen`` block. Generation never edits app.py or
existing route modules; it writes a self-contained scaffold under
``generated/<id>/`` so a human can register it deliberately.

Example node:

    {
      "rule": "/api/foo/<int:item_id>",
      "endpoint": "foo.get_item",
      "methods": ["GET"],
      "status": "planned",
      "codegen": {
        "id": "foo_get_item",
        "blueprint": "foo",
        "function": "get_item",
        "mcp_server": "search_server",
        "mcp_tool": "get_foo_item",
        "description": "Return one foo item.",
        "parameters": [
          {"name": "item_id", "in": "path", "type": "int"},
          {"name": "verbose", "in": "query", "type": "bool", "default": false}
        ]
      }
    }
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PATH_PARAM = re.compile(r"<(?:(?P<conv>[^:<>]+):)?(?P<name>[^<>]+)>")
TYPE_MAP = {"int": "int", "float": "float", "string": "str", "str": "str", "bool": "bool"}


def _python_type(value: str | None) -> str:
    return TYPE_MAP.get((value or "str").lower(), "str")


def _path_params(rule: str) -> list[dict[str, str]]:
    return [
        {"name": m.group("name"), "type": m.group("conv") or "str"}
        for m in PATH_PARAM.finditer(rule)
    ]


def _signature(rule: str, parameters: list[dict[str, Any]]) -> tuple[list[str], dict[str, Any]]:
    path = {p["name"]: p for p in _path_params(rule)}
    args: list[str] = []
    defaults: dict[str, Any] = {}
    for p in parameters:
        name = p.get("name")
        if not name:
            continue
        where = p.get("in") or ("path" if name in path else "query")
        if where == "path":
            args.append(f"{name}: {_python_type(p.get('type') or path.get(name, {}).get('type'))}")
        elif p.get("default") is not None:
            default = p["default"]
            rendered = repr(default) if not isinstance(default, bool) else str(default)
            args.append(f"{name}: {_python_type(p.get('type'))} = {rendered}")
            defaults[name] = default
        else:
            args.append(f"{name}: {_python_type(p.get('type'))}")
    return args, defaults


def _route_code(node: dict[str, Any], codegen: dict[str, Any]) -> str:
    rule = node["rule"]
    methods = [m.upper() for m in node.get("methods") or ["GET"]]
    func = codegen.get("function") or "handler"
    blueprint = codegen.get("blueprint") or "generated"
    args, _ = _signature(rule, codegen.get("parameters") or [])
    signature = ", ".join(args) if args else ""
    route_decorator = (
        f'@bp.route("{rule}", methods={methods!r})'
        if len(methods) != 1
        else f'@bp.{methods[0].lower()}("{rule}")'
    )
    return f'''"""Generated Flask skeleton for {node["rule"]}.

Generated from ARCHITECTURE.json. Register this blueprint in api_server.py
after implementing the handler.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

bp = Blueprint("{blueprint}", __name__)


{route_decorator}
def {func}({signature}):
    data = request.get_json(silent=True) or {{}}
    # TODO: implement {codegen.get("description") or node["rule"]}
    return jsonify({{"ok": False, "error": "not implemented"}}), 501
'''


def _mcp_code(node: dict[str, Any], codegen: dict[str, Any]) -> str:
    rule = node["rule"]
    methods = [m.upper() for m in node.get("methods") or ["GET"]]
    method = methods[0]
    tool = codegen.get("mcp_tool") or codegen.get("function") or "tool"
    description = codegen.get("description") or f"Generated tool for {rule}."
    params = codegen.get("parameters") or []
    args, _ = _signature(rule, params)
    signature = ", ".join(args) if args else ""
    path_params = {p["name"] for p in _path_params(rule)}
    fstring = rule
    for name in path_params:
        fstring = re.sub(rf"<[^<>]*{re.escape(name)}>", "{" + name + "}", fstring)
    payload = {
        p["name"]: p["name"]
        for p in params
        if (p.get("in") or ("path" if p["name"] in path_params else "query")) != "path"
    }
    if payload:
        payload_code = "{" + ", ".join(f'"{k}": {k}' for k in payload) + "}"
    else:
        payload_code = "None"
    return f'''"""Generated MCP tool skeleton for {rule}.

Paste this function into mcp_server/{codegen.get("mcp_server") or "search_server"}.py
and keep the import of _call.
"""

from _forward import _call


@mcp.tool(description="{description.replace('"', '\\"')}")
def {tool}({signature}) -> str:
    """{description}"""
    return _call("{method}", f"{fstring}", {payload_code})
'''


def generate(arch_path: Path, node_id: str) -> dict[str, str]:
    data = json.loads(arch_path.read_text(encoding="utf-8"))
    nodes = [
        n
        for n in data.get("api", {}).get("endpoints", [])
        if (n.get("codegen") or {}).get("id") == node_id
    ]
    if len(nodes) != 1:
        raise ValueError(f"expected exactly one codegen node {node_id!r}, found {len(nodes)}")
    node = nodes[0]
    codegen = node.get("codegen") or {}
    if not node.get("rule"):
        raise ValueError("node has no rule")
    if node.get("status") != "planned":
        raise ValueError("only status=planned nodes may be scaffolded")
    return {"route": _route_code(node, codegen), "mcp": _mcp_code(node, codegen)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arch", default=str(ROOT / "ARCHITECTURE.json"))
    parser.add_argument("--node", required=True, help="codegen.id")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    files = generate(Path(args.arch), args.node)
    out = Path(args.out_dir or (ROOT / "generated" / args.node))
    if out.exists() and not args.force:
        raise SystemExit(f"refusing to overwrite {out}; pass --force")
    out.mkdir(parents=True, exist_ok=True)
    (out / "route.py").write_text(files["route"], encoding="utf-8", newline="\n")
    (out / "mcp_tool.py").write_text(files["mcp"], encoding="utf-8", newline="\n")
    (out / "README.md").write_text(
        "# Generated scaffold\n\n"
        "1. Copy `route.py` into the target `routes/` module or register its blueprint.\n"
        "2. Copy `mcp_tool.py` into the target MCP server.\n"
        "3. Implement the handler and tool.\n"
        "4. Change `status` from `planned` to `implemented` in ARCHITECTURE.json.\n"
        "5. Run `python scripts/validate_arch.py`.\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"generated {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
