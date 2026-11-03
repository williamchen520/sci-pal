"""Pre-ingest structural audit and repair for parsed papers.

The goal is to catch broken IDs / empty paragraphs / dangling section parents
before any row reaches SQLite or PostgreSQL. Repairs are limited to identity and
shape fields; scientific text is never rewritten.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List


class PreflightError(ValueError):
    """Raised when a parsed paper cannot be safely ingested."""


@dataclass
class PreflightReport:
    paper_id: str
    source: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    repairs: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "source": self.source,
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "repairs": self.repairs,
        }


def enabled() -> bool:
    return os.environ.get("SCIPAL_INGEST_PREFLIGHT", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def _unique(raw: Any, used: set[str], prefix: str, index: int, repairs: list[str]) -> str:
    value = str(raw).strip() if raw is not None else ""
    if not value:
        value = f"{prefix}_{index:05d}"
        repairs.append(f"generated missing id: {value}")
    if value in used:
        base = value
        suffix = 2
        while f"{base}_dup{suffix}" in used:
            suffix += 1
        value = f"{base}_dup{suffix}"
        repairs.append(f"renamed duplicate id: {base} -> {value}")
    used.add(value)
    return value


def audit_and_repair(
    parsed: Dict[str, Any], paper_id: str | None = None, source: str = "unknown"
) -> PreflightReport:
    """Validate and repair a parsed paper in place.

    Errors mean the paper must not be ingested. Warnings/repairs are logged by
    the caller and do not block the write.
    """
    report = PreflightReport(paper_id=paper_id or "", source=source)
    if not isinstance(parsed, dict):
        report.errors.append("parsed payload is not an object")
        return report

    resolved_id = paper_id or parsed.get("paper_id")
    if not resolved_id:
        report.errors.append("missing paper_id")
    report.paper_id = str(resolved_id or "")

    metadata = parsed.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        report.errors.append("metadata is not an object")
        metadata = {}
    metadata = metadata or {}
    if not str(metadata.get("title") or "").strip():
        metadata["title"] = "Untitled"
        report.warnings.append("missing title; set to Untitled")
    parsed["metadata"] = metadata

    paragraphs = parsed.get("paragraphs")
    if paragraphs is None:
        paragraphs = []
        parsed["paragraphs"] = paragraphs
    if not isinstance(paragraphs, list):
        report.errors.append("paragraphs is not a list")
        return report

    used_para: set[str] = set()
    clean_paragraphs: list[Dict[str, Any]] = []
    for index, para in enumerate(paragraphs):
        if not isinstance(para, dict):
            report.warnings.append(f"dropped non-object paragraph at {index}")
            continue
        text = str(para.get("text") or para.get("text_content") or "").strip()
        if not text:
            report.warnings.append(f"dropped empty paragraph at {index}")
            continue
        para["text"] = text
        para["text_content"] = text
        para["para_id"] = _unique(
            para.get("para_id"), used_para, f"{report.paper_id}_para", index, report.repairs
        )
        try:
            sequence = int(para.get("sequence"))
        except (TypeError, ValueError):
            sequence = index
            report.repairs.append(f"set paragraph sequence: {para['para_id']}")
        para["sequence"] = sequence
        for key in ("section_level1", "section_level2", "section_level3", "section"):
            if key in para and para[key] is None:
                para[key] = ""
        clean_paragraphs.append(para)
    parsed["paragraphs"] = clean_paragraphs
    if not clean_paragraphs:
        report.warnings.append("paper has no usable paragraphs")

    sections = parsed.get("sections")
    if isinstance(sections, list):
        used_sections: set[str] = set()
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                report.warnings.append(f"dropped non-object section at {index}")
                continue
            section["section_id"] = _unique(
                section.get("section_id"), used_sections, f"{report.paper_id}_sec", index, report.repairs
            )
        for section in sections:
            if not isinstance(section, dict):
                continue
            parent = section.get("parent_id")
            if parent and parent not in used_sections:
                section["parent_id"] = None
                report.warnings.append(
                    f"dangling section parent: {section.get('section_id')} -> {parent}"
                )
    elif sections is not None:
        report.errors.append("sections is not a list")

    for key, id_key, prefix in (
        ("figures", "fig_id", "fig"),
        ("tables", "table_id", "table"),
        ("references", "citation_id", "cit"),
        ("citations", "citation_id", "cit"),
    ):
        rows = parsed.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list):
            report.errors.append(f"{key} is not a list")
            continue
        used: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                report.warnings.append(f"dropped non-object {key} row at {index}")
                continue
            row[id_key] = _unique(
                row.get(id_key), used, f"{report.paper_id}_{prefix}", index, report.repairs
            )

    return report


def require_ok(report: PreflightReport) -> None:
    if not report.ok:
        raise PreflightError("; ".join(report.errors))
