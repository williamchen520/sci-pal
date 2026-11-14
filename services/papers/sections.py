"""Fetch a paper section by inferred section_type."""

from __future__ import annotations

from typing import Any

from services.papers.reader import _display_section, paper_outline, paper_paragraphs

SECTION_TYPES = {
    "front_matter",
    "abstract",
    "results",
    "methods",
    "discussion",
    "back_matter",
    "references",
    "caption",
}


def paper_section(paper_id: str, section_type: str) -> dict[str, Any]:
    section_type = (section_type or "").strip().lower()
    if section_type not in SECTION_TYPES:
        raise ValueError(f"unknown section_type: {section_type}")
    outline = paper_outline(paper_id)
    matched = [row for row in outline if row.get("section_type") == section_type]
    if not matched:
        return {
            "paper_id": paper_id,
            "section_type": section_type,
            "status": "not_found",
            "sections": [],
        }
    all_rows = paper_paragraphs(
        paper_id,
        limit=200,
        include_captions=section_type == "caption",
    )
    by_path: dict[str, list[dict[str, Any]]] = {}
    for paragraph in all_rows:
        by_path.setdefault(_display_section(paragraph), []).append(paragraph)
    sections = []
    for row in matched:
        sections.append(
            {
                "section_path": row["section_path"],
                "first_para_id": row.get("first_para_id"),
                "paragraphs": by_path.get(row["section_path"], []),
            }
        )
    return {
        "paper_id": paper_id,
        "section_type": section_type,
        "status": "ok",
        "section_type_source": "heuristic",
        "sections": sections,
    }
