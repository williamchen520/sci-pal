"""Resolve Python call edges from text targets to code_units (P2.5)."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

import psycopg

IMPORT_FROM = re.compile(r"^\s*from\s+([.\w]+)\s+import\s+(.+)$")
IMPORT_PLAIN = re.compile(r"^\s*import\s+([.\w]+)(?:\s+as\s+(\w+))?\s*$")


@dataclass
class Unit:
    unit_id: str
    path: str
    symbol: str
    unit_type: str
    parent_unit_id: str | None = None


@dataclass
class FileInfo:
    path: str
    text: str


def module_of(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if "src" in parts:
        parts = parts[parts.index("src") + 1 :]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _relative_module(current: str, raw: str) -> str:
    dots = len(raw) - len(raw.lstrip("."))
    suffix = raw[dots:]
    base = current.split(".")[:-1]
    if dots > 1:
        base = base[: max(0, len(base) - (dots - 1))]
    parts = base + ([suffix] if suffix else [])
    return ".".join(parts)


def build_imports(files: dict[str, FileInfo]) -> dict[str, dict[str, tuple[str, str | None]]]:
    """path -> alias -> (module, imported symbol or None)."""
    out: dict[str, dict[str, tuple[str, str | None]]] = {}
    for path, info in files.items():
        aliases: dict[str, tuple[str, str | None]] = {}
        current = module_of(path)
        for line in info.text.splitlines():
            match = IMPORT_PLAIN.match(line)
            if match:
                module, alias = match.group(1), match.group(2) or match.group(1).split(".")[0]
                aliases[alias] = (module, None)
                continue
            match = IMPORT_FROM.match(line)
            if not match:
                continue
            raw_module, names = match.group(1), match.group(2).strip()
            module = _relative_module(current, raw_module) if raw_module.startswith(".") else raw_module
            names = names.strip("() ")
            for item in names.split(","):
                item = item.strip()
                if not item or item == "*":
                    continue
                parts = item.split()
                symbol = parts[0]
                alias = parts[-1] if len(parts) >= 3 and parts[-2] == "as" else symbol
                aliases[alias] = (module, symbol)
        out[path] = aliases
    return out


def resolve_target(
    *,
    source_path: str,
    target: str,
    imports: dict[str, dict[str, tuple[str, str | None]]],
    file_by_module: dict[str, str],
    symbols_by_path: dict[str, dict[str, str]],
    source_unit_id: str = "",
    parent_by_unit: dict[str, str] | None = None,
    class_methods: dict[str, dict[str, str]] | None = None,
) -> tuple[str, str] | None:
    name = target.removeprefix("unresolved:")
    if not name or name in {"dict", "list", "set", "tuple", "str", "int", "float"}:
        return None
    parts = name.split(".")
    head, tail = parts[0], parts[-1]
    aliases = imports.get(source_path, {})
    if head in {"self", "cls"} and len(parts) > 1 and parent_by_unit and class_methods:
        parent = parent_by_unit.get(source_unit_id)
        candidate = class_methods.get(parent or "", {}).get(tail)
        if candidate:
            return candidate, "high"

    direct = symbols_by_path.get(source_path, {}).get(tail)
    if direct and len(parts) == 1:
        return direct, "high"

    imported = aliases.get(head)
    if imported:
        module, symbol = imported
        module_path = file_by_module.get(module)
        if module_path:
            candidate = symbols_by_path.get(module_path, {}).get(tail if len(parts) > 1 else (symbol or tail))
            if candidate:
                return candidate, "high"
            if symbol:
                candidate = symbols_by_path.get(module_path, {}).get(symbol)
                if candidate:
                    return candidate, "medium"
        if len(parts) > 1:
            prefix = module + "."
            matches = [
                symbols_by_path[path][tail]
                for path in symbols_by_path
                if module_of(path).startswith(prefix) and tail in symbols_by_path[path]
            ]
            if len(matches) == 1:
                return matches[0], "low"
    if len(parts) > 1:
        prefix = ".".join(parts[:-1])
        module_path = file_by_module.get(prefix)
        if module_path:
            candidate = symbols_by_path.get(module_path, {}).get(tail)
            if candidate:
                return candidate, "medium"
    return None


def load(conn, library_id: str, snapshot_id: str):
    files = {
        row[0]: FileInfo(row[0], row[1] or "")
        for row in conn.execute(
            "SELECT f.path, u.text FROM code_rag.code_units u "
            "JOIN code_rag.code_files f ON f.file_id=u.file_id "
            "WHERE u.library_id=%s AND (%s='' OR u.snapshot_id=%s) AND u.unit_type='file'",
            (library_id, snapshot_id, snapshot_id),
        ).fetchall()
    }
    units = [
        Unit(row[0], row[1], row[2] or "", row[3], row[4])
        for row in conn.execute(
            "SELECT u.unit_id,f.path,u.symbol_name,u.unit_type,u.parent_unit_id FROM code_rag.code_units u "
            "JOIN code_rag.code_files f ON f.file_id=u.file_id "
            "WHERE u.library_id=%s AND (%s='' OR u.snapshot_id=%s) AND u.unit_type <> 'file'",
            (library_id, snapshot_id, snapshot_id),
        ).fetchall()
    ]
    return files, units


def resolve_library(conn, library_id: str, snapshot_id: str = "") -> dict[str, int]:
    files, units = load(conn, library_id, snapshot_id)
    symbols_by_path: dict[str, dict[str, str]] = {}
    for unit in units:
        symbols_by_path.setdefault(unit.path, {})[unit.symbol] = unit.unit_id
    file_by_module = {module_of(path): path for path in files}
    parent_by_unit = {unit.unit_id: unit.parent_unit_id for unit in units if unit.parent_unit_id}
    class_ids = {unit.unit_id for unit in units if unit.unit_type == "class"}
    class_methods: dict[str, dict[str, str]] = {}
    for unit in units:
        if unit.parent_unit_id in class_ids:
            class_methods.setdefault(unit.parent_unit_id, {})[unit.symbol] = unit.unit_id
    imports = build_imports(files)
    rows = conn.execute(
        "SELECT src_unit_id,dst_unit_id FROM code_rag.code_edges "
        "WHERE library_id=%s AND (%s='' OR src_unit_id LIKE %s) AND relation='calls' "
        "AND dst_unit_id LIKE 'unresolved:%%'",
        (library_id, snapshot_id, "unit_%"),
    ).fetchall()
    path_by_unit = {unit.unit_id: unit.path for unit in units}
    resolved = 0
    for src, dst in rows:
        path = path_by_unit.get(src)
        if not path:
            continue
        hit = resolve_target(
            source_path=path,
            target=dst,
            imports=imports,
            file_by_module=file_by_module,
            symbols_by_path=symbols_by_path,
            source_unit_id=src,
            parent_by_unit=parent_by_unit,
            class_methods=class_methods,
        )
        if not hit:
            continue
        unit_id, confidence = hit
        if unit_id == src:
            continue
        conn.execute(
            "DELETE FROM code_rag.code_edges WHERE src_unit_id=%s AND dst_unit_id=%s AND relation='calls'",
            (src, dst),
        )
        conn.execute(
            "INSERT INTO code_rag.code_edges (src_unit_id,dst_unit_id,library_id,relation,source,confidence) "
            "VALUES (%s,%s,%s,'calls','resolver',%s) ON CONFLICT DO NOTHING",
            (src, unit_id, library_id, confidence),
        )
        resolved += 1
    return {"candidates": len(rows), "resolved": resolved, "unresolved": len(rows) - resolved}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--snapshot-id", default="")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_DSN is required")
    with psycopg.connect(args.dsn) as conn:
        result = resolve_library(conn, args.library_id, args.snapshot_id)
        conn.commit()
    print(f"CODE_RAG_RESOLVE_OK candidates={result['candidates']} resolved={result['resolved']} unresolved={result['unresolved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
