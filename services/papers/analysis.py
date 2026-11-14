"""Aggregate a read-only single-paper analysis for scipal-paper."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection
from services.papers.evidence import paper_evidence
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


def analyze_paper(paper_id: str, *, query: str = "", top_k: int = 8) -> dict[str, Any] | None:
    meta = _paper_meta(paper_id)
    if not meta:
        return None
    outline = paper_outline(paper_id)
    first = paper_first_paragraph(paper_id)
    evidence = paper_evidence(paper_id, query, top_k=top_k) if query.strip() else []
    return {
        "paper": {
            "paper_id": paper_id,
            "title": meta.get("title") or "",
            "doi": meta.get("doi") or "",
            "journal": meta.get("journal") or "",
            "year": meta.get("year"),
        },
        "outline": outline,
        "first_paragraph": first,
        "evidence": evidence,
        "query": query,
        "code": {"status": "not_indexed", "reason": "code link/module map not wired in this step"},
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
