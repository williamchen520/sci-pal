"""Paper-title recall: surface papers whose *title* matches the query terms.

Paragraph retrieval drifts toward generic reviews that mention the topic in
passing; the paper title is a much stronger signal. ``papers_fts`` already
indexes titles, so this channel is cheap and deterministic (no model calls).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from services.review.query_builder import count_term_hits


def _pg_connection():
    from services.db.pg_pool import pg_connection

    return pg_connection()


def _match_query(terms: Sequence[str]) -> str:
    cleaned = [term.strip().replace('"', "") for term in terms if term and term.strip()]
    return " OR ".join(f'"{term}"' for term in cleaned)


def recall_papers_by_title(
    db_path: str | Path,
    terms: Sequence[str],
    *,
    limit: int = 8,
) -> list[str]:
    """Return paper ids whose title matches any query term, best match first."""
    ts_query = " | ".join(
        term.strip().replace('"', "") for term in terms if term and term.strip()
    )
    if not ts_query:
        return []
    pg = _pg_connection()
    try:
        rows = pg.execute(
            "SELECT paper_id FROM papers "
            "WHERE to_tsvector('english', coalesce(title,'')) "
            "@@ to_tsquery('english', %s) LIMIT %s",
            (ts_query, int(limit)),
        ).fetchall()
    except Exception:
        return []
    finally:
        pg.close()
    return [row["paper_id"] for row in rows]


def best_paragraphs(
    db_path: str | Path,
    paper_id: str,
    terms: Sequence[str],
    *,
    per_paper: int = 2,
    min_hits: int = 1,
) -> list[dict[str, Any]]:
    """Pick the paragraphs of one paper that mention the most query terms."""
    pg = _pg_connection()
    try:
        rows = pg.execute(
            "SELECT p.para_id, p.paper_id, p.section_level1, p.section_level2, "
            "p.text, pa.title AS title "
            "FROM paragraphs p JOIN papers pa ON pa.paper_id = p.paper_id "
            "WHERE p.paper_id = %s LIMIT 400",
            (paper_id,),
        ).fetchall()
    finally:
        pg.close()
    scored = []
    for row in rows:
        text = row["text"] or ""
        hits = count_term_hits(text, terms)
        if hits >= min_hits:
            item = {
                "para_id": row["para_id"],
                "paper_id": row["paper_id"],
                "section_l1": row["section_level1"] or "",
                "text": text,
                "paper_title": row["title"] or "",
            }
            scored.append((-hits, -len(text), item))
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return [entry[2] for entry in scored[:per_paper]]


def recall(db_path: str | Path, terms: Sequence[str], *, limit: int = 6) -> list[dict[str, Any]]:
    """Convenience: title matches with their best paragraphs attached."""
    results: list[dict[str, Any]] = []
    for paper_id in recall_papers_by_title(db_path, terms, limit=limit):
        paragraphs = best_paragraphs(db_path, paper_id, terms)
        if paragraphs:
            results.append({"paper_id": paper_id, "paragraphs": paragraphs})
    return results


def recall_abstracts_by_title(
    db_path: str | Path,
    terms: Sequence[str],
    *,
    limit: int = 8,
) -> list[str]:
    """Same title search, against the PostgreSQL abstracts table."""
    ts_query = " | ".join(
        term.strip().replace('"', "") for term in terms if term and term.strip()
    )
    if not ts_query:
        return []
    pg = _pg_connection()
    try:
        rows = pg.execute(
            "SELECT pmid FROM abstracts WHERE to_tsvector('english', "
            "coalesce(title,'') || ' ' || coalesce(abstract,'')) "
            "@@ to_tsquery('english', %s) LIMIT %s",
            (ts_query, int(limit)),
        ).fetchall()
    except Exception:
        return []
    finally:
        pg.close()
    return [row["pmid"] for row in rows]


def abstract_for(
    db_path: str | Path,
    pmid: str,
    terms: Sequence[str],
) -> dict[str, Any] | None:
    """Fetch one abstract, keeping it only if it mentions a query term."""
    pg = _pg_connection()
    try:
        row = pg.execute(
            "SELECT pmid, title, abstract, authors, journal, year FROM abstracts WHERE pmid = %s",
            (pmid,),
        ).fetchone()
    except Exception:
        return None
    finally:
        pg.close()
    if row is None or not (row["abstract"] or "").strip():
        return None
    if count_term_hits(row["abstract"], terms) < 1:
        return None
    return {
        "pmid": row["pmid"],
        "title": row["title"] or "",
        "abstract": row["abstract"] or "",
        "authors": row["authors"] or "",
        "journal": row["journal"] or "",
        "year": row["year"] or "",
    }
