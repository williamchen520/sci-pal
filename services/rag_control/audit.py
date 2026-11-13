"""R9: audit listing and RO-Crate evidence package export."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from services.db.pg_pool import core_connection
from services.rag_control.adjudication import get_multi


def list_adjudications(
    *, decision: str = "", rag_id: str = "", limit: int = 100
) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            """
            SELECT a.*, q.query
            FROM rag_adjudications a
            JOIN rag_multi_queries q ON q.multi_run_id = a.multi_run_id
            WHERE (%s='' OR a.decision=%s) AND (%s='' OR a.rag_id=%s)
            ORDER BY a.created_at DESC
            LIMIT %s
            """,
            (decision, decision, rag_id, rag_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [
            {
                "adjudication_id": row["adjudication_id"],
                "multi_run_id": row["multi_run_id"],
                "query": row["query"],
                "rag_id": row["rag_id"],
                "decision": row["decision"],
                "note": row["note"],
                "decided_by": row["decided_by"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]
    finally:
        pg.close()


def list_conflicts(*, rag_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
    pg = core_connection()
    try:
        rows = pg.execute(
            """
            SELECT c.*, q.query
            FROM rag_conflict_flags c
            JOIN rag_multi_queries q ON q.multi_run_id = c.multi_run_id
            WHERE (%s='' OR c.rag_id=%s)
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            (rag_id, rag_id, max(1, min(int(limit), 500))),
        ).fetchall()
        return [
            {
                "flag_id": row["flag_id"],
                "multi_run_id": row["multi_run_id"],
                "query": row["query"],
                "rag_id": row["rag_id"],
                "note": row["note"],
                "flagged_by": row["flagged_by"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]
    finally:
        pg.close()


def ro_crate(multi_run_id: str) -> bytes | None:
    run = get_multi(multi_run_id)
    if not run:
        return None
    now = datetime.now(timezone.utc).isoformat()
    evidence = []
    for group in run["groups"]:
        for item in group["evidence"]:
            evidence.append({"rag_id": group["rag_id"], **item})
    files = {
        "README.md": (
            f"# SciPal evidence package\n\n"
            f"multi_run_id: {multi_run_id}\n\n"
            f"query: {run['query']}\n\n"
            "Human adjudications and conflicts are included; machine signals are retrieval signals only.\n"
            + (
                "This package contains a signed finalization; verify with verify-seal.\n"
                if run.get("finalization")
                else "This package is not finalized.\n"
            )
        ),
        "data/evidence.json": json.dumps(evidence, ensure_ascii=False, indent=2),
        "data/adjudications.json": json.dumps(run["adjudications"], ensure_ascii=False, indent=2),
        "data/conflicts.json": json.dumps(run["conflicts"], ensure_ascii=False, indent=2),
        "data/finalization.json": json.dumps(run.get("finalization"), ensure_ascii=False, indent=2),
        "data/duplicates.json": json.dumps(
            {
                "duplicate_count": run.get("duplicate_count", 0),
                "items": [
                    {
                        "rag_id": group["rag_id"],
                        "evidence_id": item["evidence_id"],
                        "duplicate_of": item["duplicate_of"],
                    }
                    for group in run["groups"]
                    for item in group["evidence"]
                    if item.get("duplicate_of")
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
    }
    metadata = {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": f"SciPal evidence package {multi_run_id}",
                "description": run["query"],
                "datePublished": now,
                "hasPart": [{"@id": path} for path in files],
            },
            *[
                {"@id": path, "@type": "File", "name": path}
                for path in files
            ],
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ro-crate-metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def _csv(rows: list[list[Any]], headers: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_safe(value) for value in row])
    return buffer.getvalue()


def adjudications_csv() -> str:
    return _csv(
        [
            [item["created_at"], item["multi_run_id"], item["query"], item["rag_id"], item["decision"], item["decided_by"], item["note"]]
            for item in list_adjudications(limit=500)
        ],
        ["created_at", "multi_run_id", "query", "rag_id", "decision", "decided_by", "note"],
    )


def conflicts_csv() -> str:
    return _csv(
        [
            [item["created_at"], item["multi_run_id"], item["query"], item["rag_id"], item["flagged_by"], item["note"]]
            for item in list_conflicts(limit=500)
        ],
        ["created_at", "multi_run_id", "query", "rag_id", "flagged_by", "note"],
    )


def evidence_csv(multi_run_id: str) -> str | None:
    run = get_multi(multi_run_id)
    if not run:
        return None
    rows = []
    for group in run["groups"]:
        for item in group["evidence"]:
            rows.append(
                [
                    group["rag_id"],
                    item["evidence_id"],
                    item.get("source_path"),
                    item.get("start_line"),
                    item.get("end_line"),
                    item.get("score"),
                    item.get("content_hash"),
                    json.dumps(item.get("metadata") or {}, ensure_ascii=False),
                    item.get("duplicate_of", ""),
                ]
            )
    return _csv(
        rows,
        ["rag_id", "evidence_id", "source_path", "start_line", "end_line", "score", "content_hash", "metadata", "duplicate_of"],
    )
