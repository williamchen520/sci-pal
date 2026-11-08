"""PG-only link builders for paper_links and sentence_links."""

from __future__ import annotations

import hashlib
import re
from typing import Optional

from services.db.pg_pool import owner_connection


def _link_id(prefix: str, *parts: str) -> str:
    digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _normalize_title(title: str) -> str:
    text = (title or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_paper_links_for(paper_id: str) -> int:
    """Upsert citations from one paper into paper_links using PG only."""
    pg = owner_connection()
    written = 0
    try:
        rows = pg.execute(
            "SELECT paper_id, doi, title FROM papers"
        ).fetchall()
        doi_map = {str(row["doi"]).strip().lower(): row["paper_id"] for row in rows if row.get("doi")}
        title_map = {}
        for row in rows:
            key = _normalize_title(row.get("title") or "")
            if len(key) > 15:
                title_map.setdefault(key, row["paper_id"])

        citations = pg.execute(
            "SELECT citation_id, doi, title FROM citations WHERE paper_id = %s",
            (paper_id,),
        ).fetchall()
        for citation in citations:
            doi = (citation.get("doi") or "").strip().lower()
            target = doi_map.get(doi) if doi else None
            if not target:
                target = title_map.get(_normalize_title(citation.get("title") or ""))
            if not target or target == paper_id:
                continue
            link_id = _link_id("plink", paper_id, target, "cites")
            pg.execute(
                "INSERT INTO paper_links "
                "(link_id, source_paper_id, target_paper_id, target_doi, relation, "
                " evidence_sentence_id, source, confidence) "
                "VALUES (%s,%s,%s,%s,'cites',NULL,'pg_citations',1.0) "
                "ON CONFLICT (link_id) DO UPDATE SET target_paper_id=EXCLUDED.target_paper_id, "
                "target_doi=EXCLUDED.target_doi, confidence=EXCLUDED.confidence",
                (link_id, paper_id, target, doi or None),
            )
            written += 1
        pg.commit()
    finally:
        pg.close()
    return written


def build_sentence_links_for(paper_id: str) -> int:
    """Build figure/table/citation links from PG sentences for one paper."""
    pg = owner_connection()
    written = 0
    try:
        sentences = pg.execute(
            "SELECT sentence_id, para_id, paper_id, text FROM sentences WHERE paper_id = %s",
            (paper_id,),
        ).fetchall()
        figures = {
            str(row["fig_number"]): row["fig_id"]
            for row in pg.execute(
                "SELECT fig_id, fig_number FROM figures WHERE paper_id = %s", (paper_id,)
            ).fetchall()
            if row.get("fig_number")
        }
        tables = {
            str(row["table_number"]): row["table_id"]
            for row in pg.execute(
                'SELECT table_id, table_number FROM "tables" WHERE paper_id = %s', (paper_id,)
            ).fetchall()
            if row.get("table_number")
        }
        citations = {
            str(row["ref_number"]): row["citation_id"]
            for row in pg.execute(
                "SELECT citation_id, ref_number FROM citations WHERE paper_id = %s", (paper_id,)
            ).fetchall()
            if row.get("ref_number")
        }

        def add(sentence, target_type, target_id):
            nonlocal written
            relation = {
                "figure": "mentions",
                "table": "mentions",
                "citation": "cites",
            }[target_type]
            link_id = _link_id("slink", sentence["sentence_id"], target_type, str(target_id), relation)
            pg.execute(
                "INSERT INTO sentence_links "
                "(link_id, sentence_id, para_id, paper_id, source_type, target_type, "
                " target_id, relation, source, confidence) "
                "VALUES (%s,%s,%s,%s,'sentence',%s,%s,%s,'pg_links',1.0) "
                "ON CONFLICT (link_id) DO UPDATE SET target_id=EXCLUDED.target_id",
                (link_id, sentence["sentence_id"], sentence["para_id"], sentence["paper_id"],
                 target_type, str(target_id), relation),
            )
            written += 1

        for sentence in sentences:
            text = sentence.get("text") or ""
            for match in re.finditer(r"(?:Fig(?:ure)?\.?)\s*([0-9]+)", text, re.I):
                target = figures.get(match.group(1))
                if target:
                    add(sentence, "figure", target)
            for match in re.finditer(r"Table\s*([0-9]+)", text, re.I):
                target = tables.get(match.group(1))
                if target:
                    add(sentence, "table", target)
            for match in re.finditer(r"\[([0-9,\s\-]+)\]", text):
                for part in re.split(r"[,\s]+", match.group(1)):
                    if not part:
                        continue
                    if "-" in part:
                        bounds = part.split("-", 1)
                        if bounds[0].isdigit() and bounds[1].isdigit():
                            for number in range(int(bounds[0]), int(bounds[1]) + 1):
                                target = citations.get(str(number))
                                if target:
                                    add(sentence, "citation", target)
                    else:
                        target = citations.get(part)
                        if target:
                            add(sentence, "citation", target)
        pg.commit()
    finally:
        pg.close()
    return written


def build_links_for(paper_id: str) -> dict:
    return {
        "paper_links": build_paper_links_for(paper_id),
        "sentence_links": build_sentence_links_for(paper_id),
    }
