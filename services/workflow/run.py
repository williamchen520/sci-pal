"""Command line entry for the review workflow.

Usage::

    python -m services.workflow.run --spec job.json --run-dir data/runs/2026-10-25 --approve

Exit codes:

- ``0`` run completed (possibly with skips)
- ``1`` run failed, or the spec/run directory is invalid
- ``2`` approval required — re-run with ``--approve`` to continue
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from services.workflow import (
    DEFAULT_STAGES,
    WorkflowSpec,
    build_draft_stage,
    build_evidence_stage,
    build_export_stage,
    build_plan_stage,
    build_retrieve_stage,
    build_store_stage,
    build_verify_stage,
    run_workflow,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_APPROVAL_REQUIRED = 2


def load_spec(path: str | Path) -> WorkflowSpec:
    """Load a job spec from JSON (topic + outline + optional limits/stages)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("spec must be a JSON object")

    topic = str(raw.get("topic") or "").strip()
    if not topic:
        raise ValueError("spec.topic is required")

    stages = tuple(raw.get("stages") or DEFAULT_STAGES)
    metadata: dict[str, Any] = {}
    if raw.get("outline") is not None:
        metadata["outline"] = raw["outline"]

    return WorkflowSpec(
        topic=topic,
        workflow=str(raw.get("workflow") or "review-v1"),
        stages=stages,
        limits=dict(raw.get("limits") or {}),
        outputs=tuple(raw.get("outputs") or ("draft.md", "review.json")),
        metadata=metadata,
    )


def build_stages() -> dict[str, Any]:
    return {
        "plan": build_plan_stage(),
        "retrieve": build_retrieve_stage(),
        "evidence": build_evidence_stage(),
        "draft": build_draft_stage(),
        "verify": build_verify_stage(),
        "store": build_store_stage(),
        "export": build_export_stage(),
    }


def main(argv: Sequence[str] | None = None, *, stages: Mapping[str, Any] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="services.workflow.run")
    parser.add_argument("--spec", required=True, help="job spec JSON")
    parser.add_argument("--run-dir", required=True, help="directory for this run's artifacts")
    parser.add_argument("--approve", action="store_true", help="approve the plan and continue")
    parser.add_argument("--resume", action="store_true", help="continue an existing run")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--json", action="store_true", help="print the full manifest")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        spec = load_spec(args.spec)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid spec: {exc}", file=sys.stderr)
        return EXIT_FAILED

    implemented = dict(stages) if stages is not None else build_stages()
    try:
        manifest = run_workflow(
            spec,
            implemented,
            run_dir=args.run_dir,
            approve=args.approve,
            run_id=args.run_id,
            resume=args.resume,
        )
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"run failed to start: {exc}", file=sys.stderr)
        return EXIT_FAILED

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        _print_summary(manifest, Path(args.run_dir))

    if manifest["status"] == "approval_required":
        return EXIT_APPROVAL_REQUIRED
    if manifest["status"] == "failed":
        return EXIT_FAILED
    return EXIT_OK


def _print_summary(manifest: Mapping[str, Any], run_dir: Path) -> None:
    print(f"run_id : {manifest['run_id']}")
    print(f"status : {manifest['status']}")
    print(f"run_dir: {run_dir}")
    print("stages :")
    for stage in manifest["stages"]:
        elapsed = stage.get("elapsed_ms")
        suffix = f" ({elapsed} ms)" if elapsed is not None else ""
        print(f"  - {stage['name']:<9} {stage['status']}{suffix}")
    if manifest.get("errors"):
        print("errors :")
        for error in manifest["errors"]:
            print(f"  - [{error.get('kind')}] {error.get('message')}")


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())
