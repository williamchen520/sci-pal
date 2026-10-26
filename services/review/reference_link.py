"""Link review references to local papers by DOI (citations become clickable)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def normalize_doi(value) -> str:
    text = str(value or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
    return text.strip().lower()


def enrich_references(references: list, db_path: str | Path) -> list:
    """Add ``doi_url`` and, when the DOI exists locally, ``paper_id``."""
    if not references:
        return references
    connection = None
    try:
        connection = sqlite3.connect(str(db_path), timeout=5)
    except sqlite3.Error:
        connection = None
    try:
        for reference in references:
            if not isinstance(reference, dict):
                continue
            doi = normalize_doi(reference.get("doi"))
            if not doi:
                continue
            reference["doi_url"] = f"https://doi.org/{doi}"
            if connection is None:
                continue
            try:
                row = connection.execute(
                    "SELECT paper_id FROM papers WHERE lower(doi) = ? LIMIT 1", (doi,)
                ).fetchone()
            except sqlite3.Error:
                break
            if row:
                reference["paper_id"] = row[0]
    finally:
        if connection is not None:
            connection.close()
    return references
