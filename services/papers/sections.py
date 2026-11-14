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
MAX_LIMIT = 200


def paper_section(
    paper_id: str,
    section_type: str,
    *,
    include_paragraphs: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    section_type = (section_type or "").strip().lower()
    if section_type not in SECTION_TYPES:
        raise ValueError(f"unknown section_type: {section_type}")
    limit = max(1, min(int(limit), MAX_LIMIT))
    offset = max(0, int(offset))
    outline = paper_outline(paper_id)
    matched = [row for row in outline if row.get("section_type") == section_type]
    if not matched:
        return {
            "paper_id": paper_id,
            "section_type": section_type,
            "status": "not_found",
            "sections": [],
        }

    by_path: dict[str, list[dict[str, Any]]] = {}
    if include_paragraphs:
        all_rows = paper_paragraphs(
            paper_id,
            limit=200,
            include_captions=section_type == "caption",
        )
        for paragraph in all_rows:
            by_path.setdefault(_display_section(paragraph), []).append(paragraph)

    sections = []
    for row in matched:
        paragraphs = by_path.get(row["section_path"], [])
        item = {
            "section_path": row["section_path"],
            "first_para_id": row.get("first_para_id"),
            "paragraph_count": int(row.get("paragraph_count") or 0),
        }
        if include_paragraphs:
            item["paragraphs"] = paragraphs[offset : offset + limit]
            item["returned"] = len(item["paragraphs"])
            item["truncated"] = len(paragraphs) > offset + limit
        sections.append(item)
    return {
        "paper_id": paper_id,
        "section_type": section_type,
        "status": "ok",
        "section_type_source": "heuristic",
        "include_paragraphs": include_paragraphs,
        "limit": limit if include_paragraphs else 0,
        "offset": offset,
        "sections": sections,
    }
