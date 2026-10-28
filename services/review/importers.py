"""Parse BibTeX / CSV records for review project import."""

from __future__ import annotations

import csv
import io
import re
from typing import Dict, List

ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.IGNORECASE)
FIELD_RE = re.compile(r"(title|doi)\s*=\s*[{\"](.+?)[}\"]\s*,?", re.IGNORECASE | re.DOTALL)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().strip("{}").strip()


def parse_bibtex(text: str) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for match in ENTRY_RE.finditer(text or ""):
        entry_type = match.group(1).lower()
        if entry_type in ("comment", "string", "preamble"):
            continue
        start = match.end()
        end = text.find("\n@", start)
        body = text[start : end if end != -1 else len(text)]
        fields = {key.lower(): _clean(value) for key, value in FIELD_RE.findall(body)}
        title = fields.get("title", "")
        doi = fields.get("doi", "")
        if title or doi:
            records.append({"title": title, "doi": doi})
    return records


def parse_csv(text: str) -> List[Dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames:
        return []
    lookup = {name.strip().lower(): name for name in reader.fieldnames if name}
    title_key = lookup.get("title") or lookup.get("article title")
    doi_key = lookup.get("doi")
    if not title_key and not doi_key:
        return []
    records = []
    for row in reader:
        title = _clean(row.get(title_key, "")) if title_key else ""
        doi = _clean(row.get(doi_key, "")) if doi_key else ""
        if title or doi:
            records.append({"title": title, "doi": doi})
    return records


def parse_file(filename: str, text: str) -> List[Dict[str, str]]:
    lower = (filename or "").lower()
    if lower.endswith((".bib", ".bibtex")):
        return parse_bibtex(text)
    if lower.endswith((".csv", ".tsv")):
        return parse_csv(text)
    return []
