"""P2: dual-write work/document identity for newly ingested papers.

The public table write remains authoritative. Identity writes are best-effort
and must never roll back the public ingest.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from services.db.pg_pool import ingest_connection

ROOT = Path(__file__).resolve().parent.parent.parent
PDF_DIR = Path(os.environ.get("SCIPAL_DOCUMENTS_DIR", str(ROOT / "documents")))
XML_DIR = Path(os.environ.get("SCIPAL_DOCUMENTS_XML_DIR", str(ROOT / "documents_xml")))
LOG = logging.getLogger(__name__)


def _doi(value: str) -> str:
    text = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text


def _source_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return "pdf"
    if name.endswith(".xml"):
        return "xml"
    return ""


def _work_id(doi: str, paper_id: str) -> str:
    identity = f"doi:{doi}" if doi else f"paper:{paper_id}"
    return "work_" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pmcid(paper_id: str, filename: str) -> str:
    for value in (paper_id, filename):
        upper = (value or "").upper()
        if "PMC" in upper:
            digits = "".join(ch for ch in upper.split("PMC", 1)[1] if ch.isdigit())
            if digits:
                return "PMC" + digits
    return ""


def ensure_identity(
    paper_id: str,
    filename: str,
    *,
    doi: str = "",
    title: str = "",
    year: Any = None,
    parser: str = "",
    source_path: str | Path | None = None,
) -> Optional[Dict[str, str]]:
    """Upsert work/document/mapping for one paper. Returns None if file absent."""
    source_type = _source_type(filename)
    if not source_type:
        return None
    path = Path(source_path) if source_path else (PDF_DIR if source_type == "pdf" else XML_DIR) / filename
    if not path.exists():
        LOG.warning("library identity skipped, file missing: %s", path)
        return None

    sha = _sha256(path)
    clean_doi = _doi(doi)
    work_id = _work_id(clean_doi, paper_id)
    document_id = f"doc_{sha[:16]}_{source_type}_{work_id[-8:]}"
    rel = f"{'documents' if source_type == 'pdf' else 'documents_xml'}/{filename}"

    pg = ingest_connection()
    try:
        pg.execute(
            "INSERT INTO catalog.works (work_id, primary_doi, pmcid, title, year) "
            "VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT (work_id) DO UPDATE SET "
            "primary_doi=EXCLUDED.primary_doi, pmcid=EXCLUDED.pmcid, "
            "title=EXCLUDED.title, year=EXCLUDED.year",
            (work_id, clean_doi or None, _pmcid(paper_id, filename) or None, title or None, year),
        )
        pg.execute(
            "INSERT INTO library_main.documents "
            "(document_id, work_id, library_id, source_type, source_path, sha256, parser, parser_version) "
            "VALUES (%s,%s,'library_main',%s,%s,%s,%s,%s) "
            "ON CONFLICT (document_id) DO NOTHING",
            (document_id, work_id, source_type, rel, sha, parser or source_type, None),
        )
        pg.execute(
            "INSERT INTO library_main.paper_documents (paper_id, document_id) "
            "VALUES (%s,%s) ON CONFLICT (paper_id) DO UPDATE SET document_id=EXCLUDED.document_id",
            (paper_id, document_id),
        )
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
    return {"work_id": work_id, "document_id": document_id}


def ensure_from_parsed(parsed_result: Dict[str, Any]) -> Optional[Dict[str, str]]:
    meta = parsed_result.get("metadata") or {}
    return ensure_identity(
        parsed_result.get("paper_id") or meta.get("paper_id") or "",
        meta.get("filename") or parsed_result.get("filename") or "",
        doi=meta.get("doi") or "",
        title=meta.get("title") or "",
        year=meta.get("year"),
        parser=meta.get("parse_engine") or parsed_result.get("parse_engine") or "",
        source_path=parsed_result.get("source_path") or meta.get("source_path"),
    )
