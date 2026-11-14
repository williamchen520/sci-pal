"""Paper module map derived from an already-bound code library."""

from __future__ import annotations

import re
from typing import Any

import psycopg

from services.papers.bindings import _code_dsn, list_bindings


def _code_connection():
    dsn = _code_dsn()
    if not dsn:
        raise RuntimeError("SCIPAL_CODE_READ_DSN is not configured")
    return psycopg.connect(dsn, connect_timeout=10)


def _import_name(value: str) -> str:
    for prefix in ("unresolved:library:", "unresolved:", "source:", "include:"):
        if value.startswith(prefix):
            return value[len(prefix):]
    return value


_CAPABILITIES = (
    ("infercnv", "CNV inference"),
    ("cellcall", "cell-cell communication"),
    ("cellchat", "cell-cell communication"),
    ("scenic", "regulon / SCENIC"),
    ("scopeloomr", "SCENIC loom"),
    ("scmetabolism", "metabolism"),
    ("monocle", "trajectory"),
    ("singler", "cell annotation"),
    ("celldex", "reference atlas"),
    ("harmony", "batch integration"),
    ("nmf", "NMF programs"),
    ("aucell", "regulon scoring"),
    ("gsva", "pathway scoring"),
)


def _purpose(path: str, imports: list[str]) -> str:
    name = path.rsplit("/", 1)[-1]
    match = re.search(r"figure[_ .-]?(\d+)", name, re.IGNORECASE)
    parts = [f"Figure {match.group(1)} analysis"] if match else [name]
    lowered = [item.lower() for item in imports]
    for needle, label in _CAPABILITIES:
        if any(needle in item for item in lowered) and label not in parts:
            parts.append(label)
    return "; ".join(parts)


def _library_modules(library_id: str, snapshot_id: str) -> list[dict[str, Any]]:
    with _code_connection() as conn:
        files = conn.execute(
            """
            SELECT file_id, path, language
            FROM code_rag.code_files
            WHERE library_id=%s AND snapshot_id=%s
            ORDER BY path
            """,
            (library_id, snapshot_id),
        ).fetchall()
        modules = []
        for file_id, path, language in files:
            symbols = [
                row[0]
                for row in conn.execute(
                    "SELECT symbol_name FROM code_rag.code_units "
                    "WHERE file_id=%s ORDER BY start_line",
                    (file_id,),
                ).fetchall()
            ]
            edges = dict(
                conn.execute(
                    "SELECT relation, count(*) FROM code_rag.code_edges "
                    "WHERE library_id=%s AND src_unit_id IN "
                    "(SELECT unit_id FROM code_rag.code_units WHERE file_id=%s) "
                    "GROUP BY relation",
                    (library_id, file_id),
                ).fetchall()
            )
            imports = [
                _import_name(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT dst_unit_id FROM code_rag.code_edges "
                    "WHERE library_id=%s AND relation='imports' AND src_unit_id IN "
                    "(SELECT unit_id FROM code_rag.code_units WHERE file_id=%s) "
                    "ORDER BY dst_unit_id",
                    (library_id, file_id),
                ).fetchall()
            ]
            modules.append(
                {
                    "path": path,
                    "language": language,
                    "unit_count": len(symbols),
                    "symbols": symbols,
                    "imports": imports,
                    "purpose": _purpose(path, imports),
                    "purpose_source": "inferred",
                    "purpose_confidence": "low",
                    "edges": {str(k): int(v) for k, v in edges.items()},
                }
            )
        return modules


def paper_modules(paper_id: str) -> dict[str, Any]:
    bindings = list_bindings(paper_id)
    if not bindings:
        return {
            "paper_id": paper_id,
            "status": "unbound",
            "reason": "no code library binding",
            "modules": [],
        }
    modules: list[dict[str, Any]] = []
    for binding in bindings:
        try:
            modules.extend(
                _library_modules(binding["library_id"], binding["snapshot_id"] or "")
            )
        except Exception as exc:  # one broken library must not hide others
            modules.append(
                {
                    "path": "",
                    "language": "",
                    "unit_count": 0,
                    "symbols": [],
                    "edges": {},
                    "error": str(exc),
                    "library_id": binding["library_id"],
                }
            )
    return {
        "paper_id": paper_id,
        "status": "ok" if modules else "partial",
        "modules": modules,
    }
