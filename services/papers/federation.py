"""Paper-level federation view: grouped sources, never merged scores."""

from __future__ import annotations

from typing import Any

from services.db.pg_pool import corpus_connection
from services.papers.html_native import html_native
from services.papers.jats import jats_native
from services.papers.pdf_native import pdf_native
from services.papers.sources import list_sources


def _paper_meta(paper_id: str) -> dict[str, Any]:
    pg = corpus_connection()
    try:
        row = pg.execute(
            "SELECT paper_id,title,doi,journal,year FROM papers WHERE paper_id=%s",
            (paper_id,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        pg.close()


def _native_summary(source_kind: str, paper_id: str) -> dict[str, Any]:
    if source_kind == "jats":
        native = jats_native(paper_id)
        if native:
            return {
                "article_type": native.get("article_type", ""),
                "journal_title": native.get("journal_title", ""),
                "section_count": len(native.get("sections", [])),
            }
    elif source_kind == "html":
        native = html_native(paper_id)
        if native:
            return {
                "section_count": native.get("section_count", 0),
                "paragraph_count": native.get("paragraph_count", 0),
            }
    elif source_kind == "pdf":
        native = pdf_native(paper_id)
        if native:
            return {
                "page_count": native.get("page_count", 0),
                "paragraph_count": native.get("paragraph_count", 0),
            }
    return {}


def federated_paper(
    paper_id: str, *, source_kinds: list[str] | None = None
) -> dict[str, Any] | None:
    meta = _paper_meta(paper_id)
    if not meta:
        return None
    wanted = {kind.strip().lower() for kind in (source_kinds or []) if kind.strip()}
    groups: list[dict[str, Any]] = []
    for source in list_sources(paper_id):
        kind = source.get("source_kind") or ""
        if wanted and kind not in wanted:
            continue
        groups.append(
            {
                "source_kind": kind,
                "source_id": source.get("source_id"),
                "source_uri": source.get("source_uri") or "",
                "is_primary": bool(source.get("is_primary")),
                "common": {
                    "title": meta.get("title") or "",
                    "doi": meta.get("doi") or "",
                },
                "native": _native_summary(kind, paper_id),
            }
        )
    return {
        "paper_id": paper_id,
        "title": meta.get("title") or "",
        "doi": meta.get("doi") or "",
        "groups": groups,
        "source_kinds": [group["source_kind"] for group in groups],
        "policy": {
            "scope": "paper",
            "grouped": True,
            "merge_scores": False,
            "source_kinds": sorted(wanted),
        },
    }
