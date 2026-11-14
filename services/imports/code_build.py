"""Build parsed code units into the code RAG database."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import psycopg


class CodeBuildError(RuntimeError):
    """Parsed code cannot be built."""


def _stable(prefix: str, *parts: str) -> str:
    return prefix + "_" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _dsn() -> str:
    value = (
        os.environ.get("SCIPAL_CODE_DSN", "").strip()
        or os.environ.get("SCIPAL_TENANT_CODE_DSN", "").strip()
    )
    if not value:
        raise CodeBuildError("tenant code writer DSN is not configured")
    return value


def build_code(item: dict[str, Any], payload: dict[str, Any], *, dsn: str | None = None) -> dict[str, Any]:
    files = payload.get("files") or []
    if not files:
        raise CodeBuildError("parsed code payload has no files")
    library_id = str(item.get("library_id") or "")
    if not library_id:
        raise CodeBuildError("import item has no library_id")
    source_uri = str(item.get("source_uri") or "")
    dsn = dsn or _dsn()
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    source_id = _stable("src", library_id, source_uri)
    snapshot_id = _stable("snap", source_id, content_hash)
    units_written = 0
    edges_written = 0

    with psycopg.connect(dsn) as conn:
        conn.execute(
            "INSERT INTO code_rag.code_sources (source_id,library_id,repo_url,ref,license) "
            "VALUES (%s,%s,%s,'import','') ON CONFLICT (source_id) DO UPDATE SET ref='import'",
            (source_id, library_id, source_uri),
        )
        conn.execute(
            "INSERT INTO code_rag.code_snapshots "
            "(snapshot_id,source_id,library_id,commit_sha,ref) "
            "VALUES (%s,%s,%s,'import','import') ON CONFLICT (snapshot_id) DO NOTHING",
            (snapshot_id, source_id, library_id),
        )
        conn.execute("DELETE FROM code_rag.code_units WHERE snapshot_id=%s", (snapshot_id,))
        for file in files:
            rel = str(file.get("file") or "unknown")
            text = json.dumps(file, ensure_ascii=False)
            file_id = _stable("file", snapshot_id, rel)
            conn.execute(
                "INSERT INTO code_rag.code_files "
                "(file_id,snapshot_id,library_id,path,language,content_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (snapshot_id,path) DO UPDATE SET content_hash=EXCLUDED.content_hash",
                (file_id, snapshot_id, library_id, rel, file.get("language") or "unknown",
                 hashlib.sha256(text.encode()).hexdigest()),
            )
            unit_ids = {}
            for unit in file.get("units") or []:
                unit_ids[unit["unit_id"]] = _stable("unit", library_id, snapshot_id, unit["unit_id"])
            for unit in file.get("units") or []:
                conn.execute(
                    "INSERT INTO code_rag.code_units "
                    "(unit_id,snapshot_id,library_id,file_id,symbol_name,unit_type,text,"
                    "start_line,end_line,parent_unit_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (unit_id) DO NOTHING",
                    (
                        unit_ids[unit["unit_id"]],
                        snapshot_id,
                        library_id,
                        file_id,
                        unit.get("symbol_name") or "",
                        unit.get("unit_type") or "unit",
                        unit.get("text") or "",
                        unit.get("start_line") or 0,
                        unit.get("end_line") or 0,
                        unit_ids.get(unit.get("parent_unit_id"), unit.get("parent_unit_id")),
                    ),
                )
                units_written += 1
            for edge in file.get("edges") or []:
                conn.execute(
                    "INSERT INTO code_rag.code_edges "
                    "(src_unit_id,dst_unit_id,library_id,relation,source,confidence) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (
                        unit_ids.get(edge.get("src_unit_id"), edge.get("src_unit_id")),
                        unit_ids.get(edge.get("dst_unit_id"), edge.get("dst_unit_id")),
                        library_id,
                        edge.get("relation") or "unknown",
                        edge.get("source") or "parser",
                        edge.get("confidence") or "medium",
                    ),
                )
                edges_written += 1
        conn.commit()
    return {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "files": len(files),
        "units": units_written,
        "edges": edges_written,
    }
