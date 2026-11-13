"""Build a C3 evidence package for one code unit."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
from typing import Any

import psycopg


def parse_imports(text: str) -> list[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    lines = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            line = ast.get_source_segment(text, node)
            if line:
                lines.append(line.strip())
    return lines


def build_context(
    *,
    unit_id: str,
    library_id: str,
    dsn: str | None = None,
    max_neighbors: int = 10,
    direction: str = "out",
) -> dict[str, Any]:
    if direction not in {"out", "in", "both"}:
        raise ValueError("direction must be out, in, or both")
    dsn = dsn or os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
    if not dsn:
        raise SystemExit("SCIPAL_CODE_READ_DSN is required")
    with psycopg.connect(dsn) as conn:
        row = conn.execute(
            """
            SELECT u.unit_id,u.symbol_name,u.unit_type,f.path,u.start_line,u.end_line,
                   s.ref,s.package_version,u.text
            FROM code_rag.code_units u
            JOIN code_rag.code_files f ON f.file_id=u.file_id
            JOIN code_rag.code_snapshots s ON s.snapshot_id=u.snapshot_id
            WHERE u.unit_id=%s AND u.library_id=%s
            """,
            (unit_id, library_id),
        ).fetchone()
        if not row:
            raise ValueError("unit not found")
        file_row = conn.execute(
            "SELECT u.text FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
            "WHERE u.library_id=%s AND f.path=%s AND u.unit_type='file' LIMIT 1",
            (library_id, row[3]),
        ).fetchone()
        imports = parse_imports(file_row[0] if file_row else "")
        if direction == "out":
            edge_where = "src_unit_id=%s"
            edge_params = (library_id, unit_id, max_neighbors * 2)
        elif direction == "in":
            edge_where = "dst_unit_id=%s"
            edge_params = (library_id, unit_id, max_neighbors * 2)
        else:
            edge_where = "(src_unit_id=%s OR dst_unit_id=%s)"
            edge_params = (library_id, unit_id, unit_id, max_neighbors * 2)
        edges = conn.execute(
            f"SELECT src_unit_id,dst_unit_id,relation FROM code_rag.code_edges "
            f"WHERE library_id=%s AND {edge_where} LIMIT %s",
            edge_params,
        ).fetchall()
        neighbor_ids = []
        for src, dst, _ in edges:
            other = dst if src == unit_id else src
            if other.startswith("unresolved:") or other in neighbor_ids:
                continue
            neighbor_ids.append(other)
            if len(neighbor_ids) >= max_neighbors:
                break
        neighbors = []
        if neighbor_ids:
            for n in conn.execute(
                "SELECT u.unit_id,u.symbol_name,u.unit_type,f.path,u.start_line,u.end_line "
                "FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
                "WHERE u.unit_id = ANY(%s) AND u.library_id=%s",
                (neighbor_ids, library_id),
            ).fetchall():
                neighbors.append(
                    {"unit_id": n[0], "symbol_name": n[1], "unit_type": n[2], "path": n[3], "start_line": n[4], "end_line": n[5]}
                )
    return {
        "library_id": library_id,
        "unit": {
            "unit_id": row[0],
            "symbol_name": row[1],
            "unit_type": row[2],
            "path": row[3],
            "start_line": row[4],
            "end_line": row[5],
            "ref": row[6] or row[7] or "",
        },
        "direction": direction,
        "imports": imports,
        "neighbors": neighbors,
        "edges": [{"src": s, "dst": d, "relation": r} for s, d, r in edges],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("unit_id")
    parser.add_argument("--library-id", required=True)
    parser.add_argument("--dsn", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = build_context(unit_id=args.unit_id, library_id=args.library_id, dsn=args.dsn or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
