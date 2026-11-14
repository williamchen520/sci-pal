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
    re.compile(r"\bread_excel\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bread_xlsx\s*\(\s*['\"]([^'\"]+)['\"]"),
]
WRITE_PATTERNS = [
    re.compile(r"\bsaveRDS\s*\([^,]+,\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bwrite\.csv\s*\([^,]+,\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bwrite\.table\s*\([^,]+,\s*(?:file\s*=\s*)?['\"]([^'\"]+)['\"]"),
    re.compile(r"\bto_csv\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bto_parquet\s*\(\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bwrite_xlsx\s*\([^,]+,\s*['\"]([^'\"]+)['\"]"),
    re.compile(r"\bwrite_excel\s*\([^,]+,\s*['\"]([^'\"]+)['\"]"),
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


FILEPATH_CALL = re.compile(
    r"\b(read_excel|read_xlsx|write_xlsx|write_excel|readRDS|saveRDS|read\.csv|write\.csv)\s*\(([\s\S]*?)\)",
    re.IGNORECASE,
)


def _filepath_call_edges(path: str, text: str) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in FILEPATH_CALL.finditer(text):
        name, args = match.group(1).lower(), match.group(2)
        if "file.path" not in args.lower():
            continue
        literals = re.findall(r"['\"]([^'\"]+)['\"]", args)
        if not literals:
            continue
        artifact = literals[-1].strip()
        if not artifact:
            continue
        relation = "reads" if name.startswith("read") else "writes"
        key = (relation, artifact)
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            {
                "source": f"file:{path}",
                "target": f"artifact:{artifact}",
                "relation": relation,
                "confidence": "explicit",
                "method": "file.path",
            }
        )
    return edges


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
    filepath_edges = _filepath_call_edges(path, text)
    for edge in filepath_edges:
        artifact_id = edge["target"]
        if not any(node["id"] == artifact_id for node in nodes):
            nodes.append(
                {
                    "id": artifact_id,
                    "kind": "artifact",
                    "label": artifact_id.removeprefix("artifact:"),
                }
            )
    edges.extend(filepath_edges)
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
