"""Workflow runner data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

#: Default stage order. ``plan`` is a real stage (its artifact is the approval
#: gate input); ``store`` and ``export`` are split so an export failure can be
#: retried without re-writing the review.
DEFAULT_STAGES: tuple[str, ...] = (
    "plan",
    "retrieve",
    "evidence",
    "draft",
    "verify",
    "store",
    "export",
)

StageStatus = Literal["ok", "skipped", "failed"]


@dataclass(frozen=True)
class WorkflowSpec:
    topic: str
    workflow: str = "review-v1"
    stages: tuple[str, ...] = DEFAULT_STAGES
    limits: Mapping[str, Any] = field(default_factory=dict)
    outputs: tuple[str, ...] = ("draft.md", "review.json")
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.topic.strip():
            raise ValueError("topic must not be empty")
        unknown = [stage for stage in self.stages if stage not in DEFAULT_STAGES]
        if unknown:
            raise ValueError(f"Unknown workflow stage(s): {unknown}")
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("stages must not repeat")


@dataclass
class StageContext:
    run_id: str
    run_dir: Path
    spec: WorkflowSpec
    services: Mapping[str, Any]
    logger: Any


@dataclass
class StageResult:
    status: StageStatus = "ok"
    artifacts: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"ok", "skipped", "failed"}:
            raise ValueError(f"Invalid stage status: {self.status}")
