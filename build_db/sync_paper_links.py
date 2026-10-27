"""Sync existing article-level relations into the unified ``paper_links`` table.

Reads what already exists (no embedding / no network):

* ``cross_paper_index``  -> cites / similar
* ``paper_index``        -> cites / grobid_cites / mentions
* ``citations``          -> cites (DOI resolved to a local paper when possible)
* ``full_citation_edges`` -> cites (source DOI mapped to a local paper)

Idempotent: the table is rebuilt on each run, keeping the original source and
confidence so callers can filter by provenance.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def _link_id(source: str, target: str, relation: str) -> str:
    digest = hashlib.md5(f"{source}|{target}|{relation}".encode("utf-8")).hexdigest()[:16]
    return f"plink_{digest}"


def sync(db_path: Path | str = DEFAULT_DB) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    stats = {"links": 0, "resolved": 0}
    try:
        doi_to_paper: Dict[str, str] = {}
        for paper_id, doi in conn.execute(
            "SELECT paper_id, doi FROM papers WHERE doi IS NOT NULL AND doi != ''"
        ):
            doi_to_paper[str(doi).strip().lower()] = paper_id

        conn.execute("DELETE FROM paper_links")

        def add(source_paper: str, target_paper: Optional[str], target_doi: Optional[str],
                relation: str, source: str, confidence: float = 1.0) -> None:
            if not source_paper or not (target_paper or target_doi):
                return
            key = target_paper or target_doi
            conn.execute(
                "INSERT OR REPLACE INTO paper_links "
                "(link_id, source_paper_id, target_paper_id, target_doi, relation, "
                " evidence_sentence_id, source, confidence) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (
                    _link_id(source_paper, key, relation),
                    source_paper,
                    target_paper,
                    target_doi,
                    relation,
                    source,
                    confidence,
                ),
            )
            stats["links"] += 1
            if target_paper:
                stats["resolved"] += 1

        for source, target, relation, confidence in conn.execute(
            "SELECT source_paper_id, target_paper_id, relation, confidence "
            "FROM cross_paper_index"
        ):
            add(source, target, None, relation, "cross_paper_index",
                float(confidence or 1.0))

        for paper_id, target_id, relation in conn.execute(
            "SELECT paper_id, target_id, relation FROM paper_index "
            "WHERE relation IN ('cites', 'grobid_cites', 'mentions')"
        ):
            target = doi_to_paper.get(str(target_id).strip().lower())
            add(paper_id, target, None if target else str(target_id), relation,
                "paper_index", 0.7)

        for paper_id, doi in conn.execute(
            "SELECT paper_id, doi FROM citations WHERE doi IS NOT NULL AND doi != ''"
        ):
            normalized = str(doi).strip().lower()
            add(paper_id, doi_to_paper.get(normalized), normalized, "cites",
                "citations", 0.9)

        for source_doi, target_doi in conn.execute(
            "SELECT source_doi, target_doi FROM full_citation_edges "
            "WHERE source_doi IS NOT NULL AND target_doi IS NOT NULL"
        ):
            source_paper = doi_to_paper.get(str(source_doi).strip().lower())
            if not source_paper:
                continue
            target_paper = doi_to_paper.get(str(target_doi).strip().lower())
            add(source_paper, target_paper, str(target_doi).strip().lower(),
                "cites", "full_citation_edges", 0.5)

        conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    print(sync())
