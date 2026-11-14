"""H0: HTML batch ingest from a JSON manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from services.db.pg_pool import core_connection
from services.imports import session
from services.imports.orchestrator import process_import
from services.imports.paper_lane import PaperLaneAdapter


class BatchError(ValueError):
    """Invalid HTML batch manifest or input."""


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BatchError(f"cannot read manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise BatchError("manifest must be an object")
    if not str(data.get("library_id") or "").strip():
        raise BatchError("manifest.library_id is required")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise BatchError("manifest.items must be a non-empty list")
    if len(items) > 1000:
        raise BatchError("manifest.items exceeds 1000")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("staged_path"):
            raise BatchError(f"item {index} has no staged_path")
    data["_manifest_dir"] = str(manifest_path.resolve().parent)
    return data


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_built_by_hash(content_hash: str) -> dict[str, Any] | None:
    with core_connection() as pg:
        row = pg.execute(
            "SELECT import_id,item_id,status FROM import_items "
            "WHERE content_hash=%s AND status IN ('built','indexed','draft','parsed') "
            "ORDER BY updated_at DESC LIMIT 1",
            (content_hash,),
        ).fetchone()
    return dict(row) if row else None


def _prepare_items(manifest: dict[str, Any], limit: int = 0) -> list[dict[str, Any]]:
    base = Path(manifest["_manifest_dir"])
    prepared: list[dict[str, Any]] = []
    for raw in manifest["items"]:
        staged = Path(str(raw["staged_path"]))
        path = staged if staged.is_absolute() else base / staged
        path = path.resolve()
        if not path.is_file():
            raise BatchError(f"staged file not found: {path}")
        if path.suffix.lower() not in {".html", ".htm"}:
            raise BatchError(f"not an HTML file: {path}")
        fallback = str(raw.get("pdf_staged_path") or "").strip()
        if fallback:
            candidate = Path(fallback)
            candidate = candidate if candidate.is_absolute() else base / candidate
            fallback = str(candidate.resolve()) if candidate.is_file() else ""
        item = {
            "uri": str(raw.get("source_url") or path),
            "staged_path": str(path),
            "source_url": str(raw.get("source_url") or ""),
            "doi": str(raw.get("doi") or ""),
            "fallback_path": fallback,
            "content_hash": sha256_file(path),
        }
        prepared.append(item)
        if limit and len(prepared) >= limit:
            break
    return prepared


def run_batch(
    manifest: dict[str, Any],
    *,
    limit: int = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    items = _prepare_items(manifest, limit=limit)
    report: dict[str, Any] = {
        "library_id": manifest["library_id"],
        "tenant_id": str(manifest.get("tenant_id") or "default"),
        "dry_run": dry_run,
        "total": len(items),
        "duplicate": 0,
        "created": 0,
        "built": 0,
        "quarantined": 0,
        "failed": 0,
        "items": [],
    }
    to_import = []
    seen_hashes: dict[str, dict[str, Any]] = {}
    for item in items:
        existing = find_built_by_hash(item["content_hash"])
        if existing:
            report["duplicate"] += 1
            report["items"].append(
                {
                    **item,
                    "status": "duplicate",
                    "paper_id": None,
                    "error": "",
                    "duplicate_of": existing,
                }
            )
            continue
        if item["content_hash"] in seen_hashes:
            report["duplicate"] += 1
            report["items"].append(
                {
                    **item,
                    "status": "duplicate",
                    "paper_id": None,
                    "error": "",
                    "duplicate_of": seen_hashes[item["content_hash"]],
                }
            )
            continue
        seen_hashes[item["content_hash"]] = {
            "source": "batch",
            "staged_path": item["staged_path"],
        }
        to_import.append(item)

    if dry_run:
        for item in to_import:
            report["items"].append({**item, "status": "would_import"})
        return report

    if to_import:
        result = session.create_import(
            tenant_id=report["tenant_id"],
            library_id=report["library_id"],
            origin="api",
            items=to_import,
        )
        report["import_id"] = result["import_id"]
        processed = process_import(
            result["import_id"], paper_adapter=PaperLaneAdapter(build=True)
        )
        by_item = {row["item_id"]: row for row in processed["items"]}
        for index, item in enumerate(to_import, start=1):
            row = by_item.get(f"item_{index:04d}", {})
            status = row.get("status") or "failed"
            report["created"] += 1
            if status == "built":
                report["built"] += 1
            elif status == "quarantined":
                report["quarantined"] += 1
            elif status == "failed":
                report["failed"] += 1
            parsed = row.get("parsed_json") or {}
            report["items"].append(
                {
                    **item,
                    "status": status,
                    "paper_id": parsed.get("paper_id") if isinstance(parsed, dict) else None,
                    "error": row.get("error") or "",
                }
            )
        report["session_status"] = processed.get("status")
    return report


def write_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
