"""PostgreSQL-primary paper metadata writes (Phase 2, opt-in).

Only workspace assignment is migrated first. SQLite stays a mirror for FTS and
legacy readers. Fail closed when the PG backend is explicitly enabled.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class PaperWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_PAPER_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg_connection():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["SCIPAL_PG_DSN"], row_factory=dict_row)


def update_workspace(paper_id: str, workspace_id: str, *, db_path: str | Path) -> bool:
    """Update papers.workspace_id in PG, then mirror to SQLite.

    Returns False when the PG paper write backend is disabled, so callers can
    keep the legacy SQLite path.
    """
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            row = pg.execute(
                "UPDATE papers SET workspace_id = %s WHERE paper_id = %s RETURNING paper_id",
                (workspace_id, paper_id),
            ).fetchone()
            if not row:
                raise PaperWriteError("paper not found in PostgreSQL")
    except PaperWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG paper workspace update failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc

    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "UPDATE papers SET workspace_id = ? WHERE paper_id = ?",
            (workspace_id, paper_id),
        )
        conn.commit()
    finally:
        conn.close()
    return True


def update_metadata_if_exists(
    paper_id: str,
    *,
    journal: str | None,
    year: object,
    doi: str | None,
    db_path: str | Path,
) -> bool:
    """Best-effort immediate metadata sync for a paper already in PG.

    Bulk ingest inserts new rows through SQLite + outbox; those rows may not be
    in PG yet, so a missing row returns False instead of failing the batch.
    """
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            row = pg.execute(
                "UPDATE papers SET journal = %s, year = %s, doi = %s "
                "WHERE paper_id = %s RETURNING paper_id",
                (journal or "", year, doi or "", paper_id),
            ).fetchone()
        if not row:
            return False
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("PG metadata sync skipped for %s: %s", paper_id, exc)
        return False
    conn = sqlite3.connect(str(db_path), timeout=30)
    try:
        conn.execute(
            "UPDATE papers SET journal = ?, year = ?, doi = ? WHERE paper_id = ?",
            (journal or "", year, doi or "", paper_id),
        )
        conn.commit()
    finally:
        conn.close()
    return True


def _upsert_paper_row(pg, row: dict) -> None:
    pg.execute(
        "INSERT INTO papers (paper_id, filename, title, abstract, authors, parse_engine, journal, year, doi) "
        "VALUES (%(paper_id)s, %(filename)s, %(title)s, %(abstract)s, %(authors)s, "
        "'xml', %(journal)s, %(year)s, %(doi)s) "
        "ON CONFLICT (paper_id) DO UPDATE SET "
        "filename = EXCLUDED.filename, title = EXCLUDED.title, abstract = EXCLUDED.abstract, "
        "authors = EXCLUDED.authors, parse_engine = EXCLUDED.parse_engine, "
        "journal = EXCLUDED.journal, year = EXCLUDED.year, doi = EXCLUDED.doi",
        row,
    )


def upsert_paper(row: dict) -> bool:
    """PG-first paper metadata upsert for ingest."""
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            _upsert_paper_row(pg, row)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG paper upsert failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True


def write_papers_batch(papers: list[dict], children: list[tuple[str, list[dict], list[dict]]]) -> bool:
    """PG transaction for papers + paragraphs/sentences.

    Called while the SQLite transaction is still open: any PG failure rolls the
    SQLite batch back instead of leaving a half-ingested paper.
    """
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            for paper in papers:
                _upsert_paper_row(pg, paper)
            for paper_id, paragraphs, sentences in children:
                pg.execute("DELETE FROM sentences WHERE paper_id = %s", (paper_id,))
                pg.execute("DELETE FROM paragraphs WHERE paper_id = %s", (paper_id,))
                for row in paragraphs:
                    pg.execute(
                        "INSERT INTO paragraphs "
                        "(para_id, paper_id, section_level1, text, sequence, parse_engine, search_vector) "
                        "VALUES (%s, %s, %s, %s, %s, 'xml', to_tsvector('english', %s))",
                        (
                            row["para_id"], paper_id, row.get("section_level1"), row["text"],
                            row["sequence"], row["text"],
                        ),
                    )
                for row in sentences:
                    pg.execute(
                        "INSERT INTO sentences "
                        "(sentence_id, para_id, paper_id, text, sequence, search_vector) "
                        "VALUES (%s, %s, %s, %s, %s, to_tsvector('english', %s))",
                        (
                            row["sentence_id"], row["para_id"], paper_id, row["text"],
                            row["sequence"], row["text"],
                        ),
                    )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG paper batch failed; rolling back SQLite batch: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True


def replace_children(paper_id: str, paragraphs: list[dict], sentences: list[dict]) -> bool:
    """Replace a paper's paragraph/sentence rows in PG.

    Used as a best-effort batch writer after the SQLite transaction. The
    outbox remains a repair path until the whole ingest is PG-primary.
    """
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            pg.execute("DELETE FROM sentences WHERE paper_id = %s", (paper_id,))
            pg.execute("DELETE FROM paragraphs WHERE paper_id = %s", (paper_id,))
            for row in paragraphs:
                pg.execute(
                    "INSERT INTO paragraphs "
                    "(para_id, paper_id, section_level1, text, sequence, parse_engine, search_vector) "
                    "VALUES (%s, %s, %s, %s, %s, 'xml', to_tsvector('english', %s))",
                    (
                        row["para_id"], paper_id, row.get("section_level1"), row["text"],
                        row["sequence"], row["text"],
                    ),
                )
            for row in sentences:
                pg.execute(
                    "INSERT INTO sentences "
                    "(sentence_id, para_id, paper_id, text, sequence, search_vector) "
                    "VALUES (%s, %s, %s, %s, %s, to_tsvector('english', %s))",
                    (
                        row["sentence_id"], row["para_id"], paper_id, row["text"],
                        row["sequence"], row["text"],
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("PG child batch skipped for %s: %s", paper_id, exc)
        return False
    return True


def write_parsed_paper(parsed_result: dict) -> bool:
    """PG-first write for DatabaseWriter (PDF/preprint parse path)."""
    if not enabled():
        return False
    metadata = parsed_result.get("metadata", {}) or {}
    paper_id = parsed_result["paper_id"]
    paragraphs = parsed_result.get("paragraphs", []) or []
    figures = parsed_result.get("figures", []) or []
    tables = parsed_result.get("tables", []) or []
    paper = {
        "paper_id": paper_id,
        "filename": metadata.get("file_name") or metadata.get("filename") or "",
        "title": metadata.get("title", "Untitled"),
        "abstract": metadata.get("abstract", ""),
        "authors": ", ".join(metadata.get("authors", [])) if isinstance(metadata.get("authors"), list) else metadata.get("authors", ""),
        "journal": metadata.get("journal", ""),
        "year": metadata.get("year"),
        "doi": metadata.get("doi", ""),
    }
    try:
        with _pg_connection() as pg:
            _upsert_paper_row(pg, paper)
            for para in paragraphs:
                pg.execute(
                    "INSERT INTO paragraphs "
                    "(para_id, paper_id, section_level1, section_level2, section_level3, text, sequence, page, bbox, parse_engine, search_vector) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'pdf',to_tsvector('english',%s)) "
                    "ON CONFLICT (para_id) DO UPDATE SET text=EXCLUDED.text, sequence=EXCLUDED.sequence, "
                    "page=EXCLUDED.page, bbox=EXCLUDED.bbox, search_vector=EXCLUDED.search_vector",
                    (
                        para.get("para_id"), paper_id,
                        para.get("section_type") or para.get("section_level1"),
                        para.get("section_title") or para.get("section_level2"),
                        para.get("section_level3"),
                        para.get("text_content") or para.get("text") or "",
                        para.get("para_index") or para.get("sequence") or 0,
                        para.get("page_number") or para.get("page"),
                        str(para.get("bbox", "")) if para.get("bbox") else None,
                        para.get("text_content") or para.get("text") or "",
                    ),
                )
            for fig in figures:
                pg.execute(
                    "INSERT INTO figures (fig_id,paper_id,fig_number,caption,file_path,page,bbox) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (fig_id) DO UPDATE SET "
                    "caption=EXCLUDED.caption, file_path=EXCLUDED.file_path, page=EXCLUDED.page, bbox=EXCLUDED.bbox",
                    (
                        fig.get("figure_id") or fig.get("fig_id"), paper_id,
                        fig.get("figure_number") or fig.get("fig_number"),
                        fig.get("caption"), fig.get("image_path") or fig.get("file_path"),
                        fig.get("page_number") or fig.get("page"),
                        str(fig.get("bbox", "")) if fig.get("bbox") else None,
                    ),
                )
            for table in tables:
                pg.execute(
                    'INSERT INTO "tables" (table_id,paper_id,table_number,caption,markdown,page) '
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (table_id) DO UPDATE SET "
                    "caption=EXCLUDED.caption, markdown=EXCLUDED.markdown, page=EXCLUDED.page",
                    (
                        table.get("table_id"), paper_id, table.get("table_number"),
                        table.get("caption"), table.get("markdown") or table.get("table_data"),
                        table.get("page_number") or table.get("page"),
                    ),
                )
            for cit in parsed_result.get("citations", []) or []:
                pg.execute(
                    "INSERT INTO citations (citation_id,paper_id,ref_number,raw_text,doi,title,authors,journal,year,page,bbox) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (citation_id) DO UPDATE SET "
                    "raw_text=EXCLUDED.raw_text, doi=EXCLUDED.doi, title=EXCLUDED.title, "
                    "authors=EXCLUDED.authors, journal=EXCLUDED.journal, year=EXCLUDED.year",
                    (
                        cit.get("citation_id"), cit.get("paper_id") or paper_id,
                        cit.get("ref_index") or cit.get("ref_number"), cit.get("raw_text"),
                        cit.get("doi"), cit.get("title"), cit.get("author") or cit.get("authors"),
                        cit.get("journal"), cit.get("year"), cit.get("page"), cit.get("bbox"),
                    ),
                )
            for index, mention in enumerate(parsed_result.get("intext_citations") or [], 1):
                pg.execute(
                    "INSERT INTO citation_mentions (mention_id,paper_id,ref_number,page,bbox,context,source,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (mention_id) DO UPDATE SET "
                    "ref_number=EXCLUDED.ref_number, page=EXCLUDED.page, bbox=EXCLUDED.bbox, context=EXCLUDED.context",
                    (
                        f"mention_{paper_id}_{index:04d}", paper_id, mention.get("ref_number"),
                        mention.get("page"), mention.get("bbox"), mention.get("context"),
                        mention.get("source") or "grobid", datetime.now(timezone.utc).isoformat(),
                    ),
                )
            provenance = parsed_result.get("provenance")
            if provenance:
                pg.execute(
                    "INSERT INTO parse_provenance "
                    "(paper_id,text_engine,meta_engine,refs_engine,tables_engine,decision,metrics_json,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (paper_id) DO UPDATE SET "
                    "text_engine=EXCLUDED.text_engine, meta_engine=EXCLUDED.meta_engine, "
                    "refs_engine=EXCLUDED.refs_engine, tables_engine=EXCLUDED.tables_engine, "
                    "decision=EXCLUDED.decision, metrics_json=EXCLUDED.metrics_json",
                    (
                        paper_id, provenance.get("text_engine", ""), provenance.get("meta_engine", ""),
                        provenance.get("refs_engine", ""), provenance.get("tables_engine", ""),
                        provenance.get("decision", ""),
                        __import__("json").dumps(provenance.get("metrics") or {}, ensure_ascii=False),
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG parsed paper write failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True


def upsert_supplementary(row: dict) -> bool:
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            pg.execute(
                "INSERT INTO supplementary_files (supp_id,paper_id,filename,file_type,file_path,file_size,description) "
                "VALUES (%(supp_id)s,%(paper_id)s,%(filename)s,%(file_type)s,%(file_path)s,%(file_size)s,%(description)s) "
                "ON CONFLICT (supp_id) DO UPDATE SET filename=EXCLUDED.filename, file_type=EXCLUDED.file_type, "
                "file_path=EXCLUDED.file_path, file_size=EXCLUDED.file_size, description=EXCLUDED.description",
                row,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG supplementary write failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True


def replace_sections(paper_id: str, rows: list[tuple], para_map: list[tuple[str, str | None]]) -> bool:
    """PG mirror for build_sections_tree before SQLite mirror."""
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            pg.execute("DELETE FROM sections WHERE paper_id = %s", (paper_id,))
            for row in rows:
                pg.execute(
                    "INSERT INTO sections "
                    "(section_id,paper_id,parent_id,level,title,seq,page,bbox,source) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    row,
                )
            for para_id, section_id in para_map:
                pg.execute(
                    "UPDATE paragraphs SET section_id=%s WHERE para_id=%s",
                    (section_id, para_id),
                )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG sections write failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True


def replace_all_sentences(rows: list[tuple]) -> bool:
    """PG mirror for build_sentences_for_research_db (full rebuild)."""
    if not enabled():
        return False
    try:
        with _pg_connection() as pg:
            pg.execute("DELETE FROM sentences")
            pg.executemany(
                "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence,search_vector) "
                "VALUES (%s,%s,%s,%s,%s,to_tsvector('english',%s))",
                [(sid, para, paper, text, seq, text) for sid, para, paper, text, seq in rows],
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG full sentence rebuild failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True


def sync_paper_graph(conn, paper_id: str) -> bool:
    """Mirror an imported JATS paper graph from SQLite into PG.

    Called while the SQLite transaction is still open. If PG fails, the caller
    can roll back the SQLite transaction.
    """
    if not enabled():
        return False
    paper = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper_id,)).fetchone()
    if not paper:
        return False
    p = dict(paper)
    sections = [dict(r) for r in conn.execute("SELECT * FROM sections WHERE paper_id=?", (paper_id,))]
    paragraphs = [dict(r) for r in conn.execute("SELECT * FROM paragraphs WHERE paper_id=?", (paper_id,))]
    sentences = [dict(r) for r in conn.execute("SELECT * FROM sentences WHERE paper_id=?", (paper_id,))]
    figures = [dict(r) for r in conn.execute("SELECT * FROM figures WHERE paper_id=?", (paper_id,))]
    tables = [dict(r) for r in conn.execute('SELECT * FROM "tables" WHERE paper_id=?', (paper_id,))]
    citations = [dict(r) for r in conn.execute("SELECT * FROM citations WHERE paper_id=?", (paper_id,))]
    links = [dict(r) for r in conn.execute("SELECT * FROM sentence_links WHERE paper_id=?", (paper_id,))]
    try:
        with _pg_connection() as pg:
            for table in ("sentence_links", "sentences", "citations", "figures", "tables", "sections", "paragraphs"):
                pg.execute(f'DELETE FROM "{table}" WHERE paper_id=%s', (paper_id,))
            _upsert_paper_row(
                pg,
                {
                    "paper_id": paper_id,
                    "filename": p.get("filename") or "",
                    "title": p.get("title") or "Untitled",
                    "abstract": p.get("abstract") or "",
                    "authors": p.get("authors") or "",
                    "journal": p.get("journal") or "",
                    "year": p.get("year"),
                    "doi": p.get("doi") or "",
                },
            )
            for row in sections:
                pg.execute(
                    "INSERT INTO sections (section_id,paper_id,parent_id,level,title,seq,page,bbox,source) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (section_id) DO NOTHING",
                    (row["section_id"], paper_id, row.get("parent_id"), row.get("level"), row.get("title"),
                     row.get("seq"), row.get("page"), row.get("bbox"), row.get("source")),
                )
            for row in paragraphs:
                pg.execute(
                    "INSERT INTO paragraphs (para_id,paper_id,section_level1,section_level2,section_level3,text,sequence,page,bbox,parse_engine,section_path,section_id,search_vector) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,to_tsvector('english',%s))",
                    (row["para_id"], paper_id, row.get("section_level1"), row.get("section_level2"),
                     row.get("section_level3"), row["text"], row.get("sequence"), row.get("page"),
                     row.get("bbox"), row.get("parse_engine"), row.get("section_path"), row.get("section_id"), row["text"]),
                )
            for row in sentences:
                pg.execute(
                    "INSERT INTO sentences (sentence_id,para_id,paper_id,text,sequence,page,bbox,section_id,char_start,char_end,search_vector) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,to_tsvector('english',%s))",
                    (row["sentence_id"], row["para_id"], paper_id, row["text"], row["sequence"],
                     row.get("page"), row.get("bbox"), row.get("section_id"), row.get("char_start"), row.get("char_end"), row["text"]),
                )
            for row in figures:
                pg.execute(
                    "INSERT INTO figures (fig_id,paper_id,fig_number,caption,file_path,page,bbox) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (row["fig_id"], paper_id, row.get("fig_number"), row.get("caption"), row.get("file_path"), row.get("page"), row.get("bbox")),
                )
            for row in tables:
                pg.execute(
                    'INSERT INTO "tables" (table_id,paper_id,table_number,caption,markdown,page) VALUES (%s,%s,%s,%s,%s,%s)',
                    (row["table_id"], paper_id, row.get("table_number"), row.get("caption"), row.get("markdown"), row.get("page")),
                )
            for row in citations:
                pg.execute(
                    "INSERT INTO citations (citation_id,paper_id,ref_number,raw_text,doi,title,authors,journal,year) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (row["citation_id"], paper_id, row.get("ref_number"), row.get("raw_text"), row.get("doi"),
                     row.get("title"), row.get("authors"), row.get("journal"), row.get("year")),
                )
            for row in links:
                pg.execute(
                    "INSERT INTO sentence_links (link_id,sentence_id,para_id,paper_id,source_type,target_type,target_id,relation,page,bbox,source,confidence) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (link_id) DO NOTHING",
                    (row["link_id"], row["sentence_id"], row["para_id"], paper_id, row.get("source_type"),
                     row.get("target_type"), row.get("target_id"), row.get("relation"), row.get("page"),
                     row.get("bbox"), row.get("source"), row.get("confidence")),
                )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG imported graph sync failed; refusing SQLite fallback: %s", exc)
        raise PaperWriteError("paper write backend unavailable") from exc
    return True
