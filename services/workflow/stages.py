"""Stage implementations for the review workflow.

This batch wires the three stages that do not need models:

- ``plan``    validate the outline and write ``plan.json`` (approval input);
- ``store``   persist the review record (adapter injected; default is a JSON
              store so the pipeline runs before the DB adapter exists);
- ``export``  write deliverables (adapter injected; default copies Markdown).

``retrieve`` / ``evidence`` / ``draft`` / ``verify`` stay unimplemented here on
purpose: they need the retrieval stack and the LLM, and will be wired one at a
time with their own tests.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from services.workflow.runner import write_artifact
from services.workflow.types import StageContext, StageResult

SaveReview = Callable[[Mapping[str, Any], StageContext], Mapping[str, Any]]
ExportReview = Callable[[Mapping[str, Any], StageContext], list[str]]


def build_plan_stage() -> Callable[[StageContext], StageResult]:
    """Validate the outline and freeze the run plan."""

    def stage(context: StageContext) -> StageResult:
        sections = _sections(context.spec.metadata.get("outline"))
        if not sections:
            return _failed("invalid_input", "outline has no sections")
        plan = {
            "schema_version": "1",
            "run_id": context.run_id,
            "topic": context.spec.topic,
            "workflow": context.spec.workflow,
            "sections": sections,
            "stages": [
                {"name": name, "expected_artifacts": _expected_artifacts(name)}
                for name in context.spec.stages
            ],
            "limits": dict(context.spec.limits),
            "created_at": _now(),
        }
        write_artifact(context, "plan.json", plan)
        return StageResult(artifacts=["plan.json"], metrics={"sections": len(sections)})

    return stage


def build_store_stage(save_review: SaveReview | None = None) -> Callable[[StageContext], StageResult]:
    """Persist the reviewed draft. Reads ``review.json``, writes ``store.json``."""
    saver = save_review or _json_store

    def stage(context: StageContext) -> StageResult:
        review = _read_json(context.run_dir / "review.json")
        if review is None:
            return _failed("invalid_input", "review.json is missing; draft/verify must run first")
        record = saver(review, context)
        write_artifact(context, "store.json", dict(record))
        return StageResult(
            artifacts=["store.json"],
            metrics={"review_id": record.get("review_id")},
        )

    return stage


def build_export_stage(export_review: ExportReview | None = None) -> Callable[[StageContext], StageResult]:
    """Export deliverables. Reads ``store.json``, writes under ``exports/``."""
    exporter = export_review or _markdown_export

    def stage(context: StageContext) -> StageResult:
        record = _read_json(context.run_dir / "store.json")
        if record is None:
            return _failed("invalid_input", "store.json is missing; store must run first")
        artifacts = exporter(record, context)
        return StageResult(artifacts=list(artifacts), metrics={"files": len(artifacts)})

    return stage


# ---------------------------------------------------------------------------
# Default adapters (replaceable without touching the runner or the stages)
# ---------------------------------------------------------------------------


def _json_store(review: Mapping[str, Any], context: StageContext) -> dict[str, Any]:
    """Placeholder store: keeps the record next to the run until the DB adapter lands."""
    record = {
        "review_id": f"rev_{uuid.uuid4().hex[:12]}",
        "topic": review.get("topic") or context.spec.topic,
        "stored_at": _now(),
        "review": dict(review),
    }
    write_artifact(context, "review_store.json", record)
    return record


def _markdown_export(record: Mapping[str, Any], context: StageContext) -> list[str]:
    """Write the reviewed Markdown plus a small manifest under ``exports/``."""
    source = context.run_dir / "draft.md"
    markdown = source.read_text(encoding="utf-8") if source.exists() else ""

    exports = context.run_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    (exports / "review.md").write_text(markdown, encoding="utf-8")
    (exports / "metadata.json").write_text(
        json.dumps(
            {
                "review_id": record.get("review_id"),
                "topic": record.get("topic"),
                "exported_at": _now(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return ["exports/review.md", "exports/metadata.json"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sections(outline: Any) -> list[dict[str, Any]]:
    if not isinstance(outline, Mapping):
        return []
    raw = outline.get("sections")
    if not isinstance(raw, list):
        return []

    sections: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        section_id = str(item.get("id") or item.get("section_id") or f"sec-{index:02d}")
        keywords = item.get("keywords") or []
        if isinstance(keywords, str):
            keywords = [part for part in re.split(r"[,;，；]", keywords) if part.strip()]
        sections.append(
            {
                "id": section_id,
                "title": title,
                "keywords": [str(word).strip() for word in keywords if str(word).strip()],
            }
        )
    return sections


def _expected_artifacts(stage: str) -> list[str]:
    return {
        "plan": ["plan.json"],
        "retrieve": ["retrieve.json"],
        "evidence": ["evidence.json"],
        "draft": ["draft.md", "review.json"],
        "verify": ["verify.json"],
        "store": ["store.json"],
        "export": ["exports/review.md"],
    }.get(stage, [])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _failed(kind: str, message: str) -> StageResult:
    return StageResult(
        status="failed",
        errors=[{"kind": kind, "message": message, "retryable": False}],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
