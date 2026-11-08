"""Link review references to local papers by DOI (citations become clickable)."""

from __future__ import annotations

from services.db.pg_pool import main_read_connection


def normalize_doi(value) -> str:
    text = str(value or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    return text.strip().lower()


def enrich_references(references: list, db_path=None) -> list:
    """Add ``doi_url`` and, when the DOI exists locally, ``paper_id``."""
    if not references:
        return references
    pg = main_read_connection()
    try:
        for reference in references:
            if not isinstance(reference, dict):
                continue
            doi = normalize_doi(reference.get("doi"))
            if not doi:
                continue
            reference["doi_url"] = f"https://doi.org/{doi}"
            row = pg.execute(
                "SELECT paper_id FROM papers WHERE lower(doi) = %s LIMIT 1", (doi,)
            ).fetchone()
            if row:
                reference["paper_id"] = row["paper_id"]
    finally:
        pg.close()
    return references
