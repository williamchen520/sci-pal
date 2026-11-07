"""Paper-title recall: surface papers whose *title* matches the query terms.

Paragraph retrieval drifts toward generic reviews that mention the topic in
passing; the paper title is a much stronger signal. ``papers_fts`` already
indexes titles, so this channel is cheap and deterministic (no model calls).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from services.review.query_builder import count_term_hits


def _pg_enabled() -> bool:
    return os.environ.get("SCIPAL_SEARCH_META_BACKEND", "").strip().lower() in {
        "postgres", "postgresql", "pg", "1", "true"
    }


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
    query = _match_query(terms)
    if not query:
        return []
    if _pg_enabled():
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
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        rows = conn.execute(
            "SELECT paper_id FROM papers_fts WHERE papers_fts MATCH ? LIMIT ?",
            (query, int(limit)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [row[0] for row in rows]


def best_paragraphs(
    db_path: str | Path,
    paper_id: str,
    terms: Sequence[str],
    *,
    per_paper: int = 2,
    min_hits: int = 1,
) -> list[dict[str, Any]]:
    """Pick the paragraphs of one paper that mention the most query terms."""
    if _pg_enabled():
        pg = _pg_connection()
        try:
            rows = pg.execute(
                "SELECT p.para_id, p.paper_id, p.section_level1, p.section_level2, "
                "p.text, pa.title AS title "
                "FROM paragraphs p JOIN papers pa ON pa.paper_id = p.paper_id "
                "WHERE p.paper_id = %s LIMIT 400",
                (paper_id,),
            ).fetchall()
        except Exception:
            return []
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

    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT para_id, paper_id, section_level1, section_level2, text, "
            "(SELECT title FROM papers p WHERE p.paper_id = paragraphs.paper_id) AS title "
            "FROM paragraphs WHERE paper_id = ? LIMIT 400",
            (paper_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    scored: list[tuple[int, int, dict[str, Any]]] = []
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
    """Same title search, against ``abstracts.db`` (papers without full text)."""
    query = _match_query(terms)
    if not query:
        return []
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        rows = conn.execute(
            "SELECT pmid FROM papers_fts WHERE papers_fts MATCH ? LIMIT ?",
            (query, int(limit)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    return [row[0] for row in rows]


def abstract_for(
    db_path: str | Path,
    pmid: str,
    terms: Sequence[str],
) -> dict[str, Any] | None:
    """Fetch one abstract, keeping it only if it mentions a query term."""
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT pmid, title, abstract, authors, journal, year FROM papers WHERE pmid = ?",
            (pmid,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()

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
