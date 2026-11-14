"""Read-only paper outline / paragraph / sentence access for scipal-paper."""

from __future__ import annotations

import re
from typing import Any

from services.db.pg_pool import corpus_connection

MAX_PARAGRAPHS = 200
_GENERIC_SECTION = {"body", "article", "main", "text", ""}


def _display_section(row: dict[str, Any]) -> str:
    level1 = str(row.get("section_level1") or "").strip()
    level2 = str(row.get("section_level2") or "").strip()
    parts = []
    for part in (level1, level2):
        if part and part.lower() not in _GENERIC_SECTION and part not in parts:
            parts.append(part)
    return " > ".join(parts) or "(untitled)"


def _outline_rows(paper_id: str) -> list[dict[str, Any]]:
    pg = corpus_connection()
    try:
        rows = pg.execute(
            """
            SELECT
              COALESCE(section_path,
                       NULLIF(concat_ws(' > ', section_level1, section_level2), '')) AS section_path,
              section_level1,
              section_level2,
              section_type,
              count(*) AS paragraph_count,
              min(sequence) AS first_sequence,
              (array_agg(para_id ORDER BY sequence))[1] AS first_para_id
            FROM paragraphs
            WHERE paper_id = %s
            GROUP BY section_path, section_level1, section_level2, section_type
            ORDER BY first_sequence
            """,
            (paper_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def _section_bounds(paper_id: str) -> dict[str, Any]:
    pg = corpus_connection()
    try:
        row = pg.execute(
            """
            SELECT
              max(p.sequence) FILTER (WHERE
                btrim(COALESCE(p.section_level2,'')) = COALESCE(pa.title,'')
              ) AS abstract_end,
              min(p.sequence) FILTER (WHERE
                lower(p.section_level1) = 'discussion'
                OR strpos(lower(COALESCE(p.section_level2,'')), 'discussion') > 0
              ) AS discussion_seq,
              min(p.sequence) FILTER (WHERE
                lower(COALESCE(p.section_level2,'')) IN (
                  'data availability','code availability','references',
                  'acknowledgements','author contributions','funding',
                  'competing interests','additional information'
                )
                OR lower(p.section_level1) = 'references'
              ) AS back_seq
            FROM paragraphs p
            JOIN papers pa ON pa.paper_id = p.paper_id
            WHERE p.paper_id = %s
            """,
            (paper_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        pg.close()


def _section_type(row: dict[str, Any], bounds: dict[str, Any]) -> str:
    level1 = str(row.get("section_level1") or "").lower()
    level2 = str(row.get("section_level2") or "").lower()
    seq = int(row.get("first_sequence") or 0)
    if level1 in {"references", "reference"} or "references" in level2:
        return "references"
    if level1 in {"figure_caption", "table_caption"}:
        return "caption"
    if re.match(r"^(fig\.?|figure|table)\s+\d+", level2):
        return "caption"
    if level1 == "abstract" or "abstract" in level2:
        return "abstract"
    if level1 == "discussion" or "discussion" in level2:
        return "discussion"
    discussion = bounds.get("discussion_seq")
    back = bounds.get("back_seq")
    abstract_end = bounds.get("abstract_end")
    if discussion is not None and seq > int(discussion):
        if back is not None and seq >= int(back):
            return "back_matter"
        return "methods"
    if discussion is not None and seq < int(discussion):
        if abstract_end is not None and seq <= int(abstract_end):
            return "front_matter"
        return "results"
    return "front_matter"


def paper_outline(paper_id: str) -> list[dict[str, Any]]:
    bounds = _section_bounds(paper_id)
    merged: dict[str, dict[str, Any]] = {}
    for row in _outline_rows(paper_id):
        path = _display_section(row)
        first_sequence = int(row.get("first_sequence") or 0)
        stored_type = row.get("section_type") or ""
        current = merged.get(path)
        if current is None or first_sequence < current["first_sequence"]:
            merged[path] = {
                "section_path": path,
                "section_level1": row.get("section_level1") or "",
                "section_level2": row.get("section_level2") or "",
                "paragraph_count": int(row.get("paragraph_count") or 0),
                "first_para_id": row.get("first_para_id"),
                "first_sequence": first_sequence,
                "section_type": stored_type or _section_type(row, bounds),
                "section_type_source": "stored" if stored_type else "heuristic",
            }
        else:
            current["paragraph_count"] += int(row.get("paragraph_count") or 0)
    return sorted(merged.values(), key=lambda row: row["first_sequence"])


def _section_clause(section: str) -> tuple[str, tuple[Any, ...]]:
    section = (section or "").strip()
    if not section:
        return "", ()
    return (
        " AND (section_level1 ILIKE %s OR section_level2 ILIKE %s OR section_path ILIKE %s)",
        (f"%{section}%", f"%{section}%", f"%{section}%"),
    )


def paper_paragraphs(
    paper_id: str,
    *,
    section: str = "",
    offset: int = 0,
    limit: int = 50,
    include_captions: bool = False,
    skip_boilerplate: bool = True,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), MAX_PARAGRAPHS))
    offset = max(0, int(offset))
    clause, params = _section_clause(section)
    clause = clause.replace('section_', 'p.section_')
    if not include_captions:
        clause += (
            " AND p.section_level1 NOT IN ('figure_caption','table_caption')"
            " AND p.text !~* '^(Fig\\.?|Figure|Table)\\s+[0-9]+\\s*\\|'"
            " AND COALESCE(p.section_level2,'') !~* '^(Fig\\.?|Figure|Table)\\s+[0-9]+'"
            " AND COALESCE(p.section_path,'') !~* '(^|>\\s*)(Fig\\.?|Figure|Table)\\s+[0-9]+'"
        )
    if skip_boilerplate:
        clause += (
            " AND p.text ~ '[A-Za-z]' AND length(btrim(p.text)) >= 20"
            " AND p.text !~* '^\\s*(https?://|doi:|www\\.)'"
            " AND p.text !~* '^\\s*(received|accepted|published|check for updates|article|open access|a list of authors|correspondence|these authors contributed)'"
        )
    pg = corpus_connection()
    try:
        rows = pg.execute(
            f"""
            SELECT p.para_id, p.paper_id, p.sequence, p.text, p.page, p.bbox,
                   p.section_id, p.section_level1, p.section_level2, p.section_path,
                   (SELECT count(*) FROM sentences s WHERE s.para_id = p.para_id) AS sentence_count
            FROM paragraphs p
            WHERE p.paper_id = %s{clause}
            ORDER BY p.sequence
            OFFSET %s LIMIT %s
            """,
            (paper_id, *params, offset, limit),
        ).fetchall()
        section_key = section.strip().lower()
        if not rows and section_key in {"results", "methods"}:
            if section_key == "results":
                bound = (
                    "p.sequence < COALESCE(("
                    "SELECT min(sequence) FROM paragraphs WHERE paper_id = %s "
                    "AND (strpos(lower(section_level2), 'discussion') > 0 "
                    "OR lower(section_level1) = 'discussion')"
                    "), 2147483647)"
                )
                bound_params = (paper_id,)
            else:
                bound = (
                    "p.sequence > COALESCE(("
                    "SELECT min(sequence) FROM paragraphs WHERE paper_id = %s "
                    "AND (strpos(lower(section_level2), 'discussion') > 0 "
                    "OR lower(section_level1) = 'discussion')"
                    "), 0) "
                    "AND p.sequence < COALESCE(("
                    "SELECT min(sequence) FROM paragraphs WHERE paper_id = %s "
                    "AND (lower(section_level2) IN ("
                    "'data availability','code availability','references',"
                    "'acknowledgements','author contributions','funding',"
                    "'competing interests','additional information') "
                    "OR lower(section_level1) = 'references')"
                    "), 2147483647)"
                )
                bound_params = (paper_id, paper_id)
            rows = pg.execute(
                f"""
                SELECT p.para_id, p.paper_id, p.sequence, p.text, p.page, p.bbox,
                       p.section_id, p.section_level1, p.section_level2, p.section_path,
                       (SELECT count(*) FROM sentences s WHERE s.para_id = p.para_id) AS sentence_count
                FROM paragraphs p
                JOIN papers pa ON pa.paper_id = p.paper_id
                WHERE p.paper_id = %s
                  AND p.section_level1 = 'body'
                  AND p.section_level2 IS NOT NULL
                  AND btrim(p.section_level2) <> COALESCE(pa.title, '')
                  AND lower(btrim(p.section_level2)) NOT IN (
                    'article','abstract','code availability','data availability',
                    'references','acknowledgements','author contributions','funding',
                    'competing interests','additional information','reporting summary'
                  )
                  AND p.text ~ '[A-Za-z]'
                  AND length(btrim(p.text)) >= 20
                  AND {bound}
                ORDER BY p.sequence
                OFFSET %s LIMIT %s
                """,
                (paper_id, *bound_params, offset, limit),
            ).fetchall()
            for row in rows:
                row["section_fallback"] = "body_headings"
        return [dict(row) for row in rows]
    finally:
        pg.close()


def paper_first_paragraph(
    paper_id: str,
    *,
    section: str = "",
    include_captions: bool = False,
    skip_boilerplate: bool = True,
) -> dict[str, Any] | None:
    rows = paper_paragraphs(
        paper_id,
        section=section,
        offset=0,
        limit=1,
        include_captions=include_captions,
        skip_boilerplate=skip_boilerplate,
    )
    return rows[0] if rows else None


def paragraph_sentences(paper_id: str, para_id: str) -> list[dict[str, Any]]:
    pg = corpus_connection()
    try:
        rows = pg.execute(
            """
            SELECT sentence_id, para_id, paper_id, text, sequence, page, bbox,
                   section_id, char_start, char_end
            FROM sentences
            WHERE paper_id = %s AND para_id = %s
            ORDER BY sequence
            """,
            (paper_id, para_id),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
