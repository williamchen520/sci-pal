"""P1 backfill: public.papers -> catalog.works + library_main.documents.

Dry-run is read-only. --apply writes only the new P0/P1 tables.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db.pg_pool import pg_connection

PDF_DIR = Path("/app/documents")
XML_DIR = Path("/app/documents_xml")


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
        if value and "PMC" in value.upper():
            token = value.upper().split("PMC", 1)[1]
            digits = "".join(ch for ch in token if ch.isdigit())
            if digits:
                return "PMC" + digits
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--pdf-dir", default=str(PDF_DIR))
    parser.add_argument("--xml-dir", default=str(XML_DIR))
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    xml_dir = Path(args.xml_dir)

    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT paper_id, filename, doi, title, year, parse_engine FROM papers ORDER BY paper_id"
        ).fetchall()
        works = {}
        documents = {}
        mappings = {}
        missing = []
        duplicates = {}

        for row in rows:
            paper_id = row["paper_id"]
            filename = row["filename"] or ""
            doi = _doi(row["doi"])
            work_id = _work_id(doi, paper_id)
            works[work_id] = {
                "work_id": work_id,
                "primary_doi": doi or None,
                "pmcid": _pmcid(paper_id, filename) or None,
                "title": row["title"],
                "year": row["year"],
            }
            source_type = _source_type(filename)
            if not source_type:
                missing.append((paper_id, filename, "no_source_type"))
                continue
            path = (pdf_dir if source_type == "pdf" else xml_dir) / filename
            if not path.exists():
                missing.append((paper_id, filename, "file_missing"))
                continue
            sha = _sha256(path)
            doc_id = f"doc_{sha[:16]}_{source_type}_{work_id[-8:]}"
            documents[doc_id] = {
                "document_id": doc_id,
                "work_id": work_id,
                "library_id": "library_main",
                "source_type": source_type,
                "source_path": f"{'documents' if source_type == 'pdf' else 'documents_xml'}/{filename}",
                "sha256": sha,
                "parser": row["parse_engine"] or source_type,
                "parser_version": None,
            }
            mappings[paper_id] = doc_id
            duplicates.setdefault((work_id, source_type, sha), []).append(paper_id)

    finally:
        pg.close()

    dup_groups = {key: ids for key, ids in duplicates.items() if len(ids) > 1}
    print(
        f"papers={len(rows)} works={len(works)} documents={len(documents)} "
        f"mappings={len(mappings)} missing={len(missing)} duplicate_file_groups={len(dup_groups)}"
    )
    for item in missing[:10]:
        print("MISSING", item)
    for key, ids in list(dup_groups.items())[:10]:
        print("DUP", key[1], len(ids), ids)

    if not args.apply:
        print("dry-run: no writes")
        return 0 if not missing else 0

    pg = pg_connection()
    try:
        for work in works.values():
            pg.execute(
                "INSERT INTO catalog.works (work_id, primary_doi, pmcid, title, year) "
                "VALUES (%s,%s,%s,%s,%s) "
                "ON CONFLICT (work_id) DO UPDATE SET "
                "primary_doi=EXCLUDED.primary_doi, pmcid=EXCLUDED.pmcid, "
                "title=EXCLUDED.title, year=EXCLUDED.year",
                (work["work_id"], work["primary_doi"], work["pmcid"], work["title"], work["year"]),
            )
        for doc in documents.values():
            pg.execute(
                "INSERT INTO library_main.documents "
                "(document_id, work_id, library_id, source_type, source_path, sha256, parser, parser_version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (document_id) DO NOTHING",
                (
                    doc["document_id"], doc["work_id"], doc["library_id"], doc["source_type"],
                    doc["source_path"], doc["sha256"], doc["parser"], doc["parser_version"],
                ),
            )
        for paper_id, document_id in mappings.items():
            pg.execute(
                "INSERT INTO library_main.paper_documents (paper_id, document_id) "
                "VALUES (%s,%s) ON CONFLICT (paper_id) DO UPDATE SET document_id=EXCLUDED.document_id",
                (paper_id, document_id),
            )
        pg.commit()
        print("apply: committed")
    except Exception:
        pg.rollback()
        raise
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
