"""External citation edges for ``paper_links``.

Two sources:

* Crossref reference lists (DOIs)  -> source='crossref_refs', confidence 0.8
* OpenAlex referenced_works (ids)  -> resolved to DOIs, source='openalex_refs', 0.9

Only local papers with a DOI are processed. Rows keep ``target_doi`` so edges
to works outside the corpus remain usable.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

from services.search.metadata_sources import (
    crossref_work,
    openalex_resolve_ids,
    openalex_work,
)

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"


def _link_id(source: str, target: str, relation: str) -> str:
    digest = hashlib.md5(f"{source}|{target}|{relation}".encode("utf-8")).hexdigest()[:16]
    return f"plink_{digest}"


def _insert(
    conn: sqlite3.Connection,
    source_paper: str,
    target_doi: str,
    relation: str,
    source: str,
    confidence: float,
    local_dois: Dict[str, str],
) -> bool:
    doi = target_doi.strip().lower()
    if not doi or doi == (conn.execute(
        "SELECT doi FROM papers WHERE paper_id = ?", (source_paper,)
    ).fetchone()[0] or "").lower():
        return False
    target_paper = local_dois.get(doi)
    link_id = _link_id(source_paper, doi, relation)
    existing = conn.execute(
        "SELECT confidence FROM paper_links WHERE link_id = ?", (link_id,)
    ).fetchone()
    if existing and float(existing[0] or 0) >= confidence:
        return False
    conn.execute(
        "INSERT OR REPLACE INTO paper_links "
        "(link_id, source_paper_id, target_paper_id, target_doi, relation, "
        " evidence_sentence_id, source, confidence) "
        "VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
        (
            link_id,
            source_paper,
            target_paper,
            doi,
            relation,
            source,
            confidence,
        ),
    )
    return True


def build(
    db_path: Path | str = DEFAULT_DB,
    source: str = "both",
    limit: int = 50,
    dry_run: bool = False,
    pause: float = 0.2,
) -> Dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    stats: Dict[str, Any] = {
        "papers": 0,
        "crossref_edges": 0,
        "openalex_edges": 0,
        "failed": 0,
        "no_match": 0,
    }
    try:
        local_dois = {
            str(row[0]).strip().lower(): row[1]
            for row in conn.execute(
                "SELECT doi, paper_id FROM papers WHERE COALESCE(doi,'') != ''"
            )
        }
        rows = conn.execute(
            "SELECT paper_id, doi FROM papers "
            "WHERE COALESCE(doi,'') != '' ORDER BY paper_id LIMIT ?",
            (limit,),
        ).fetchall()

        for row in rows:
            stats["papers"] += 1
            paper_id, doi = row["paper_id"], row["doi"]
            if source in ("crossref", "both"):
                try:
                    meta = crossref_work(doi)
                    inserts = [
                        ref["doi"]
                        for ref in meta.get("references", [])
                        if ref.get("doi")
                    ]
                    for ref_doi in inserts:
                        if not dry_run and _insert(
                            conn, paper_id, ref_doi, "cites", "crossref_refs", 0.8, local_dois
                        ):
                            stats["crossref_edges"] += 1
                        elif dry_run:
                            stats["crossref_edges"] += 1
                except Exception:  # noqa: BLE001
                    stats["failed"] += 1
            if source in ("openalex", "both"):
                try:
                    meta = openalex_work(doi)
                    ids = meta.get("referenced_works") or []
                    resolved = openalex_resolve_ids(ids[:50])
                    for ref_doi in resolved.values():
                        if not dry_run and _insert(
                            conn, paper_id, ref_doi, "cites", "openalex_refs", 0.9, local_dois
                        ):
                            stats["openalex_edges"] += 1
                        elif dry_run:
                            stats["openalex_edges"] += 1
                except Exception:  # noqa: BLE001
                    stats["failed"] += 1
            time.sleep(pause)
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--source", choices=["crossref", "openalex", "both"], default="both")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.db, source=args.source, limit=args.limit, dry_run=args.dry_run),
            ensure_ascii=False,
        )
    )
