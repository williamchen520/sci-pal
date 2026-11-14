"""Aggregate a read-only single-paper analysis for scipal-paper."""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.db.pg_pool import corpus_connection
from services.papers.bindings import list_bindings
from services.papers.code_links import list_links
from services.papers.evidence import paper_evidence
from services.papers.flow import paper_data_flow
from services.papers.reader import paper_first_paragraph, paper_outline


def _paper_meta(paper_id: str) -> dict[str, Any]:
    pg = corpus_connection()
    try:
        row = pg.execute(
            "SELECT paper_id, title, doi, journal, year FROM papers WHERE paper_id=%s",
            (paper_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        pg.close()


def analyze_paper(
    paper_id: str, *, query: str = "", top_k: int = 8, compact: bool = False
) -> dict[str, Any] | None:
    meta = _paper_meta(paper_id)
    if not meta:
        return None
    outline = paper_outline(paper_id)
    first = paper_first_paragraph(paper_id)
    evidence = paper_evidence(paper_id, query, top_k=top_k) if query.strip() else []
    links = list_links(paper_id)
    bindings = list_bindings(paper_id)
    data_flow = paper_data_flow(paper_id) if bindings else {"status": "unbound", "nodes": [], "edges": []}
    if compact:
        type_counts = Counter(row.get("section_type") or "unknown" for row in outline)
        data_flow = {
            "status": data_flow.get("status", "unknown"),
            "nodes_count": len(data_flow.get("nodes", [])),
            "edges_count": len(data_flow.get("edges", [])),
            "method": data_flow.get("method", ""),
        }
    result = {
        "paper": {
            "paper_id": paper_id,
            "title": meta.get("title") or "",
            "doi": meta.get("doi") or "",
            "journal": meta.get("journal") or "",
            "year": meta.get("year"),
        },
        "outline": [] if compact else outline,
        "outline_summary": {
            "section_count": len(outline),
            "by_type": dict(type_counts) if compact else {},
            "sections": [
                {
                    "section_path": row.get("section_path"),
                    "section_type": row.get("section_type"),
                    "paragraph_count": row.get("paragraph_count"),
                }
                for row in outline
            ]
            if compact
            else [],
        },
        "first_paragraph": first,
        "evidence": evidence,
        "data_flow": data_flow,
        "query": query,
        "code": {
            "status": "bound" if bindings else ("candidate" if links else "not_indexed"),
            "links": links,
            "bindings": bindings,
            "reason": "" if bindings else ("no valid code library binding" if links else "no code link"),
        },
        "compact": compact,
        "status": "ok" if outline else "partial",
        "gaps": [
            gap
            for gap in (
                "" if outline else "no outline",
                "" if first else "no paragraph",
                "" if evidence or not query else "no evidence",
            )
            if gap
        ],
    }
    return result
