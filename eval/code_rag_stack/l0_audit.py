"""L0 audit: AST/span/delimiter/parent validity for indexed code units."""

from __future__ import annotations

import argparse
import ast
import json
import os
import textwrap
from pathlib import Path

import psycopg


def _nextflow_balanced(text: str) -> bool:
    from code_rag.parsers import _match_brace

    start = text.find("{")
    if start == -1:
        return False
    return _match_brace(text, start) == len(text) - 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", ""))
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")

    with psycopg.connect(args.dsn) as conn:
        rows = conn.execute(
            """
            SELECT u.unit_id, u.symbol_name, u.unit_type, f.path, u.text,
                   u.start_line, u.end_line, u.parent_unit_id
            FROM code_rag.code_units u
            JOIN code_rag.code_files f ON f.file_id=u.file_id
            """
        ).fetchall()

    file_text = {
        row[3]: row[4] or ""
        for row in rows
        if row[2] == "file"
    }
    known_ids = {row[0] for row in rows}
    total = len(rows)
    stats = {
        "total": total,
        "parse_ok": 0,
        "span_exact": 0,
        "delimiter_balance": 0,
        "parent_ok": 0,
    }
    by_type: dict[str, int] = {}
    failures = []
    for unit_id, symbol, unit_type, path, text, start, end, parent in rows:
        by_type[unit_type] = by_type.get(unit_type, 0) + 1
        reasons = []
        if unit_type == "file":
            parse_ok = True
            balanced = True
            span_ok = True
        elif path.endswith(".py"):
            try:
                ast.parse(textwrap.dedent(text or ""))
                parse_ok = True
            except SyntaxError:
                parse_ok = False
                reasons.append("python_parse")
            balanced = parse_ok
            expected = "".join((file_text.get(path) or "").splitlines(keepends=True)[start - 1 : end])
            span_ok = (text or "").strip() == expected.strip()
        else:
            balanced = _nextflow_balanced(text or "")
            parse_ok = balanced
            expected = "".join((file_text.get(path) or "").splitlines(keepends=True)[start - 1 : end])
            span_ok = (text or "").strip() == expected.strip()
        parent_ok = unit_type == "file" or (parent in known_ids)
        stats["parse_ok"] += int(parse_ok)
        stats["span_exact"] += int(span_ok)
        stats["delimiter_balance"] += int(balanced)
        stats["parent_ok"] += int(parent_ok)
        if not (parse_ok and span_ok and balanced and parent_ok):
            failures.append(
                {
                    "unit_id": unit_id,
                    "symbol": symbol,
                    "type": unit_type,
                    "path": path,
                    "start": start,
                    "end": end,
                    "parse_ok": parse_ok,
                    "span_exact": span_ok,
                    "delimiter_balance": balanced,
                    "parent_ok": parent_ok,
                    "reasons": reasons,
                }
            )

    rates = {
        key: round(value / total, 4) if total else 0.0
        for key, value in stats.items()
        if key != "total"
    }
    report = {"stats": stats, "rates": rates, "by_type": by_type, "failures": failures[:50]}
    print(json.dumps({"stats": stats, "rates": rates, "by_type": by_type, "failure_count": len(failures)}, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
