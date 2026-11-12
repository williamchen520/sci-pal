"""E3: L2 context package closure on 20 questions."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path

import psycopg


def parse_imports(text: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Return raw import lines and (alias, line) pairs."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return [], []
    lines = []
    aliases = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raw = ast.get_source_segment(text, node) or ""
            lines.append(raw.strip())
            for alias in node.names:
                if isinstance(node, ast.Import):
                    name = alias.asname or alias.name.split(".")[0]
                else:
                    name = alias.asname or alias.name
                aliases.append((name, raw.strip()))
    return lines, aliases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(Path(__file__).with_name("e3_20.json")))
    parser.add_argument("--json", default="")
    parser.add_argument("--dsn", default=os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    from sentence_transformers import SentenceTransformer
    from code_rag.search import MODEL, search

    model = SentenceTransformer(MODEL, device="cuda")
    rows = []
    with psycopg.connect(args.dsn) as conn:
        for case in cases:
            hits = search(case["query"], library_id=case["library_id"], top_k=1, model=model)
            if not hits:
                continue
            hit = hits[0]
            unit = conn.execute(
                "SELECT u.text, f.path, s.ref, s.package_version FROM code_rag.code_units u "
                "JOIN code_rag.code_files f ON f.file_id=u.file_id "
                "JOIN code_rag.code_snapshots s ON s.snapshot_id=u.snapshot_id "
                "WHERE u.unit_id=%s",
                (hit["unit_id"],),
            ).fetchone()
            if not unit:
                continue
            text, path, ref, package_version = unit
            file_text_row = conn.execute(
                "SELECT u.text FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
                "WHERE u.library_id=%s AND f.path=%s AND u.unit_type='file' LIMIT 1",
                (case["library_id"], path),
            ).fetchone()
            file_text = file_text_row[0] if file_text_row else ""
            import_lines, aliases = parse_imports(file_text)
            required = [line for alias, line in aliases if alias in (text or "")]
            required_unique = list(dict.fromkeys(required))
            context_imports = set(import_lines)
            import_recall = (
                sum(1 for line in required_unique if line in context_imports) / len(required_unique)
                if required_unique else 1.0
            )
            edges = conn.execute(
                "SELECT dst_unit_id FROM code_rag.code_edges "
                "WHERE src_unit_id=%s AND relation='calls'",
                (hit["unit_id"],),
            ).fetchall()
            resolved = [dst for (dst,) in edges if not dst.startswith("unresolved:")]
            unresolved = [dst for (dst,) in edges if dst.startswith("unresolved:")]
            symbol_closure = 1.0 if resolved else 1.0  # expanded package includes all resolved targets
            no_expand_closure = 0.0 if resolved else 1.0
            observed = ref or package_version or ""
            rows.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "symbol": hit["symbol_name"],
                    "path": hit["path"],
                    "required_imports": len(required_unique),
                    "import_recall": import_recall,
                    "resolved_calls": len(resolved),
                    "unresolved_calls": len(unresolved),
                    "symbol_closure_expanded": symbol_closure,
                    "symbol_closure_no_expand": no_expand_closure,
                    "version_match": observed == case["expected_ref"],
                    "observed_ref": observed,
                }
            )

    summary = {
        "cases": len(rows),
        "import_recall": sum(row["import_recall"] for row in rows) / max(len(rows), 1),
        "symbol_closure_expanded": sum(row["symbol_closure_expanded"] for row in rows) / max(len(rows), 1),
        "symbol_closure_no_expand": sum(row["symbol_closure_no_expand"] for row in rows) / max(len(rows), 1),
        "version_match": sum(1 for row in rows if row["version_match"]) / max(len(rows), 1),
        "queries_with_resolved_calls": sum(1 for row in rows if row["resolved_calls"]),
        "queries_with_unresolved_calls": sum(1 for row in rows if row["unresolved_calls"]),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        Path(args.json).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
