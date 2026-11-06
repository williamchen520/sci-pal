#!/usr/bin/env python3
"""Extract SQL strings from Python and classify against sqlglot dialects."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import sqlglot

ROOT = Path(__file__).resolve().parent.parent
SKIP = ("venv_sciPal_py312", "__pycache__", ".git", "node_modules")
SQL_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|WITH|CREATE|ALTER|DROP)\b", re.I)
SQL_ANY = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|WITH)\b", re.I)
CALLS = {"execute", "executemany", "query", "read_sql", "exec_driver_sql"}


def _string(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, False
    if isinstance(node, ast.JoinedStr):
        parts = []
        dynamic = False
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("{}")
                dynamic = True
        return "".join(parts), dynamic
    return None, False


def _parse(sql: str, dialect: str) -> tuple[bool, str]:
    try:
        sqlglot.parse(sql, read=dialect)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:240]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="eval/results/pg_sql_extract.json")
    args = parser.parse_args()

    found = {}
    for path in ROOT.rglob("*.py"):
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if any(x in rel for x in SKIP) or rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            sql = None
            dynamic = False
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in CALLS and node.args:
                    sql, dynamic = _string(node.args[0])
            if not sql and isinstance(node, ast.Constant) and isinstance(node.value, str):
                if SQL_START.search(node.value):
                    sql, dynamic = node.value, False
            if not sql:
                continue
            sql = sql.strip()
            if len(sql) < 12 or not SQL_ANY.search(sql):
                continue
            key = hashlib.sha1(sql.encode("utf-8")).hexdigest()
            if (rel, key) in found:
                continue
            found[(rel, key)] = {
                "file": rel,
                "line": getattr(node, "lineno", 0),
                "sql": sql,
                "dynamic": dynamic,
            }

    rows = []
    for item in found.values():
        sql = item["sql"]
        pg_sql = sql.replace("?", "%s")
        lite_sql = sql.replace("%s", "?")
        pg_ok, pg_err = _parse(pg_sql, "postgres")
        lite_ok, lite_err = _parse(lite_sql, "sqlite")
        if pg_ok and lite_ok:
            kind = "portable"
        elif lite_ok:
            kind = "sqlite_only"
        elif pg_ok:
            kind = "postgres_only"
        else:
            kind = "unparsed"
        rows.append(
            {
                **item,
                "kind": kind,
                "pg_ok": pg_ok,
                "sqlite_ok": lite_ok,
                "pg_error": pg_err,
                "sqlite_error": lite_err,
            }
        )

    summary = Counter(r["kind"] for r in rows)
    by_module = defaultdict(Counter)
    for row in rows:
        by_module[row["file"].split("/")[0]][row["kind"]] += 1
    payload = {
        "total": len(rows),
        "summary": dict(summary),
        "by_module": {k: dict(v) for k, v in by_module.items()},
        "rows": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(rows), "summary": dict(summary)}, ensure_ascii=False))
    for kind in ("sqlite_only", "postgres_only", "unparsed"):
        print(f"\n## {kind}")
        for row in [r for r in rows if r["kind"] == kind][:15]:
            err = row["pg_error"] if kind != "sqlite_only" else row["sqlite_error"]
            print(f"{row['file']}:{row['line']} {row['sql'][:90]!r} | {err[:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
