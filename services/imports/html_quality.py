"""H2: HTML quality gate before canonical build."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class QualityRejected(RuntimeError):
    """Parsed HTML is too low quality to build."""


@dataclass(frozen=True)
class QualityResult:
    ok: bool
    score: int
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": self.score,
            "issues": self.issues,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


def evaluate_html(payload: dict[str, Any]) -> QualityResult:
    issues: list[str] = []
    warnings: list[str] = []
    title = str(payload.get("title") or "").strip()
    abstract = str(payload.get("abstract") or "").strip()
    sections = payload.get("sections") or []
    paragraphs = [
        str(paragraph)
        for section in sections
        for paragraph in (section.get("paragraphs") or [])
        if str(paragraph).strip()
    ]
    titles = [str(section.get("title") or "").strip() for section in sections]
    total_chars = sum(len(paragraph) for paragraph in paragraphs)

    if len(title) < 10 or title.lower() in {"untitled", "unknown"}:
        issues.append("title missing or too short")
    if len(abstract) < 100:
        issues.append(f"abstract too short ({len(abstract)} chars)")
    if len(sections) < 3:
        issues.append(f"too few sections ({len(sections)})")
    if len(paragraphs) < 5:
        issues.append(f"too few paragraphs ({len(paragraphs)})")
    if total_chars < 1000:
        issues.append(f"too little text ({total_chars} chars)")
    if not str(payload.get("doi") or "").strip():
        warnings.append("doi missing")
    if len(titles) != len(set(titles)):
        warnings.append("duplicate section titles")

    metrics = {
        "title_chars": len(title),
        "abstract_chars": len(abstract),
        "sections": len(sections),
        "paragraphs": len(paragraphs),
        "total_chars": total_chars,
    }
    score = max(
        0,
        100
        - 20 * len(issues)
        - 5 * len(warnings),
    )
    return QualityResult(
        ok=not issues,
        score=score,
        issues=issues,
        warnings=warnings,
        metrics=metrics,
    )
