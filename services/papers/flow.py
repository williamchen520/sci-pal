"""Static data-flow edges extracted from bound code files."""

from __future__ import annotations

import re
from typing import Any

from services.papers.bindings import list_bindings
from services.papers.modules import _code_connection

READ_PATTERNS = [
    re.compile(r"\breadRDS\s*\(\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bread\.csv\s*\(\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bread\.table\s*\(\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bfread\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bread_csv\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bread_parquet\s*\(\s*['\"]([^'\"]+)['\"]"),
]
WRITE_PATTERNS = [
    re.compile(r"\bsaveRDS\s*\([^,]+,\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bwrite\.csv\s*\([^,]+,\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bwrite\.table\s*\([^,]+,\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bto_csv\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bto_parquet\s*\(\s*['\"]([^'\"]+)['\"]"),
]


def _files(library_id: str, snapshot_id: str) -> list[tuple[str, str, str]]:
    with _code_connection() as conn:
        return [
            (row[0], row[1] or "", row[2] or "")
            for row in conn.execute(
                "SELECT f.path, f.language, u.text "
                "FROM code_rag.code_files f "
                "JOIN code_rag.code_units u ON u.file_id=f.file_id "
                "WHERE f.library_id=%s AND f.snapshot_id=%s AND u.unit_type='file' "
                "ORDER BY f.path",
                (library_id, snapshot_id),
            ).fetchall()
        ]


def _extract(path: str, language: str, text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = [
        {"id": f"file:{path}", "kind": "file", "label": path, "language": language}
    ]
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for relation, patterns in (("reads", READ_PATTERNS), ("writes", WRITE_PATTERNS)):
        for pattern in patterns:
            for match in pattern.finditer(text):
                artifact = match.group(1).strip()
                if not artifact:
                    continue
                key = (relation, path, artifact)
                if key in seen:
                    continue
                seen.add(key)
                artifact_id = f"artifact:{artifact}"
                nodes.append(
                    {"id": artifact_id, "kind": "artifact", "label": artifact}
                )
                edges.append(
                    {
                        "source": f"file:{path}",
                        "target": artifact_id,
                        "relation": relation,
                        "confidence": "explicit",
                        "method": "regex",
                    }
                )
    return nodes, edges


def paper_data_flow(paper_id: str) -> dict[str, Any]:
    bindings = list_bindings(paper_id)
    if not bindings:
        return {"paper_id": paper_id, "status": "unbound", "nodes": [], "edges": []}
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for binding in bindings:
        try:
            files = _files(binding["library_id"], binding["snapshot_id"] or "")
        except Exception as exc:
            return {
                "paper_id": paper_id,
                "status": "error",
                "error": str(exc),
                "nodes": [],
                "edges": [],
            }
        for path, language, text in files:
            file_nodes, file_edges = _extract(path, language, text)
            for node in file_nodes:
                nodes[node["id"]] = node
            edges.extend(file_edges)
    return {
        "paper_id": paper_id,
        "status": "ok",
        "nodes": list(nodes.values()),
        "edges": edges,
        "method": "static regex; dynamic calls unresolved",
    }
