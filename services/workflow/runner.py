"""Deterministic, resumable workflow runner.

Design goals (see ``docs/workflow-runner-design.md``):

- stages only communicate through files written under ``run_dir``;
- ``run.json`` is the single source of truth and is updated after every stage;
- a crash mid-run leaves a manifest from which ``resume=True`` can continue;
- nothing is retried silently: failures are recorded with ``kind``/``retryable``.

This module is pure orchestration. Stage implementations are injected, which is
what makes the state machine testable without models or a database.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from services.workflow.types import (
    DEFAULT_STAGES,
    StageContext,
    StageResult,
    WorkflowSpec,
)

Stage = Callable[[StageContext], StageResult]

APPROVAL_ARTIFACT = "plan.json"


def run_workflow(
    spec: WorkflowSpec,
    stages: Mapping[str, Stage],
    *,
    run_dir: str | Path,
    services: Mapping[str, Any] | None = None,
    approve: bool = False,
    run_id: str | None = None,
    resume: bool = False,
    logger: Any = None,
) -> dict[str, Any]:
    """Execute ``spec.stages`` in order and return the run manifest."""
    missing = [name for name in spec.stages if name not in stages]
    if missing:
        raise ValueError(f"Missing stage implementation(s): {missing}")

    log = logger or logging.getLogger(__name__)
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "run.json"

    manifest = _load_manifest(manifest_path) if resume else _new_manifest(spec, run_id)
    if manifest["run_id"] != (run_id or manifest["run_id"]):
        raise ValueError("run_id does not match the existing manifest")

    manifest["approval"]["approved"] = manifest["approval"]["approved"] or approve
    manifest["status"] = "running"
    _write_json(manifest_path, manifest)

    for name in spec.stages:
        state = _stage_state(manifest, name)
        if state["status"] == "ok":
            continue

        if name in {"retrieve", "evidence", "draft", "verify", "store", "export"}:
            if manifest["approval"]["required"] and not manifest["approval"]["approved"]:
                manifest["status"] = "approval_required"
                _touch(manifest, completed=False)
                _write_json(manifest_path, manifest)
                return manifest

        started = datetime.now(timezone.utc)
        context = StageContext(
            run_id=manifest["run_id"],
            run_dir=directory,
            spec=spec,
            services=dict(services or {}),
            logger=log,
        )
        try:
            result = stages[name](context)
            if not isinstance(result, StageResult):
                raise TypeError(f"stage {name} returned {type(result)!r}")
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
            log.exception("workflow stage failed: %s", name)
            result = StageResult(
                status="failed",
                errors=[{"kind": "internal", "message": str(exc), "retryable": False}],
            )

        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        state.update(
            {
                "status": result.status,
                "started_at": started.isoformat().replace("+00:00", "Z"),
                "elapsed_ms": elapsed_ms,
                "artifacts": list(result.artifacts),
                "metrics": dict(result.metrics),
                "errors": list(result.errors),
                "reason": result.reason,
            }
        )
        manifest["artifacts"] = _merge(manifest["artifacts"], result.artifacts)
        if result.errors:
            manifest["errors"].extend({"stage": name, **error} for error in result.errors)

        if result.status == "failed" and not spec.limits.get("continue_on_error", False):
            manifest["status"] = "failed"
            _touch(manifest, completed=False)
            _write_json(manifest_path, manifest)
            return manifest

        _write_json(manifest_path, manifest)

    failed = any(state["status"] == "failed" for state in manifest["stages"])
    skipped = any(state["status"] == "skipped" for state in manifest["stages"])
    manifest["status"] = "completed_with_skips" if (failed or skipped) else "completed"
    _touch(manifest, completed=True)
    _write_json(manifest_path, manifest)
    return manifest


def write_artifact(context: StageContext, name: str, payload: Any) -> str:
    """Write ``payload`` (JSON or text) atomically and return the relative path."""
    path = context.run_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        _atomic_write(path, payload.encode("utf-8"))
    else:
        _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    return name


def _new_manifest(spec: WorkflowSpec, run_id: str | None) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "run_id": run_id or str(uuid.uuid4()),
        "workflow": spec.workflow,
        "topic": spec.topic,
        "status": "pending",
        "started_at": _now(),
        "completed_at": None,
        "approval": {"required": True, "approved": False},
        "stages": [
            {
                "name": name,
                "status": "pending",
                "started_at": None,
                "elapsed_ms": None,
                "artifacts": [],
                "metrics": {},
                "errors": [],
                "reason": None,
            }
            for name in spec.stages
        ],
        "artifacts": [],
        "errors": [],
        "metadata": dict(spec.metadata),
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"cannot resume: {path} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_state(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    for state in manifest["stages"]:
        if state["name"] == name:
            return state
    raise ValueError(f"stage {name} is not part of this run")


def _touch(manifest: dict[str, Any], *, completed: bool) -> None:
    if completed:
        manifest["completed_at"] = _now()


def _merge(items: list[str], incoming: list[str]) -> list[str]:
    return list(dict.fromkeys([*items, *incoming]))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
