"""Bounded code graph traversal (read-only)."""

from __future__ import annotations

import os
from collections import deque
from typing import Any

import psycopg


def _dsn() -> str:
    value = os.environ.get("SCIPAL_CODE_READ_DSN") or os.environ.get("SCIPAL_CODE_DSN", "")
    if not value:
        raise SystemExit("SCIPAL_CODE_READ_DSN or SCIPAL_CODE_DSN is required")
    return value


def trace(
    *,
    unit_id: str,
    library_id: str,
    direction: str = "both",
    max_hops: int = 2,
    max_nodes: int = 30,
    dsn: str | None = None,
) -> dict[str, Any]:
    if direction not in {"out", "in", "both"}:
        raise ValueError("direction must be out, in, or both")
    max_hops = max(1, min(int(max_hops), 3))
    max_nodes = max(1, min(int(max_nodes), 50))
    dsn = dsn or _dsn()
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "SELECT src_unit_id, dst_unit_id, relation, confidence "
            "FROM code_rag.code_edges WHERE library_id=%s",
            (library_id,),
        ).fetchall()

    adjacency: dict[str, list[tuple[str, str, str]]] = {}
    for src, dst, relation, confidence in rows:
        if direction in {"out", "both"}:
            adjacency.setdefault(src, []).append((dst, relation, "out"))
        if direction in {"in", "both"}:
            adjacency.setdefault(dst, []).append((src, relation, "in"))

    visited = {unit_id}
    paths = []
    queue = deque([(unit_id, [unit_id], [])])
    while queue and len(visited) < max_nodes:
        current, path, edges = queue.popleft()
        if len(path) > max_hops:
            continue
        for neighbor, relation, direction_value in adjacency.get(current, []):
            edge = {"src": current, "dst": neighbor, "relation": relation, "direction": direction_value}
            if neighbor not in visited:
                visited.add(neighbor)
                paths.append(edge)
                queue.append((neighbor, path + [neighbor], edges + [edge]))
            elif edge not in paths:
                paths.append(edge)
            if len(visited) >= max_nodes:
                break

    known = {item for item in visited if not item.startswith("unresolved:")}
    nodes = []
    if known:
        with psycopg.connect(dsn) as conn:
            rows = conn.execute(
                "SELECT u.unit_id, u.symbol_name, u.unit_type, u.start_line, u.end_line, f.path "
                "FROM code_rag.code_units u JOIN code_rag.code_files f ON f.file_id=u.file_id "
                "WHERE u.unit_id = ANY(%s) AND u.library_id=%s",
                (list(known), library_id),
            ).fetchall()
            nodes = [
                {
                    "unit_id": row[0],
                    "symbol_name": row[1],
                    "unit_type": row[2],
                    "start_line": row[3],
                    "end_line": row[4],
                    "path": row[5],
                }
                for row in rows
            ]
    return {
        "library_id": library_id,
        "start": unit_id,
        "max_hops": max_hops,
        "nodes": nodes,
        "edges": paths[:max_nodes * 2],
        "truncated": len(visited) >= max_nodes,
    }
