"""Bibliographic (field-level) verification for references.

This is *not* ``services.review.citation_verifier``:

- ``citation_verifier`` answers "does this sentence have valid evidence?" (claim level).
- this module answers "is this reference real and are its fields correct?" (metadata level).

Adapted from ``nature-academic-search`` (MIT, wp-a) ``verification.py``.
Kept dependency-free so it can run inside API, CLI and MCP boundaries.

Status vocabulary (stable, do not rename):

- ``verified``      every provided field matched
- ``mismatch``      at least one provided field differed
- ``manual_needed`` nothing comparable, or some fields missing/uncheckable
- ``not_found``     the identifier lookup returned no record at all
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping, Sequence

#: Fields we can compare for a paper record.
PUBLICATION_FIELDS = frozenset(
    {
        "title",
        "authors",
        "year",
        "journal",
        "doi",
        "pmid",
        "pmcid",
        "arxiv_id",
        "openalex_id",
        "semantic_scholar_id",
    }
)

#: Public aliases accepted from callers, mapped to the stored field name.
FIELD_ALIASES = {"first_author": "authors"}

IDENTIFIER_FIELDS = frozenset(
    {"doi", "pmid", "pmcid", "arxiv_id", "openalex_id", "semantic_scholar_id"}
)


def verify_metadata(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare caller-provided metadata with a resolved record.

    Only the fields present in ``expected`` are checked; the result never
    claims more than that. Unknown fields are reported as ``uncheckable``
    instead of being silently ignored.
    """
    if actual is None:
        return {"status": "not_found", "fields": {}, "method": "identifier_lookup"}

    fields: dict[str, dict[str, Any]] = {}
    for raw_field, expected_value in expected.items():
        if raw_field in {"entity_type", "record_id"}:
            continue
        if expected_value in (None, "", [], {}):
            continue

        field = FIELD_ALIASES.get(raw_field, raw_field)
        if field not in PUBLICATION_FIELDS:
            fields[raw_field] = {"status": "uncheckable"}
            continue

        actual_value = actual.get(field)
        if actual_value in (None, "", [], {}):
            fields[raw_field] = {"status": "missing"}
            continue

        if _values_match(field, expected_value, actual_value):
            fields[raw_field] = {"status": "match"}
        else:
            fields[raw_field] = {
                "status": "mismatch",
                "expected": expected_value,
                "actual": actual_value,
            }

    statuses = {item["status"] for item in fields.values()}
    if "mismatch" in statuses:
        status = "mismatch"
    elif not fields or statuses & {"missing", "uncheckable"}:
        status = "manual_needed"
    else:
        status = "verified"

    return {"status": status, "fields": fields, "method": "identifier_lookup"}


def canonical_identifier(field: str, value: Any) -> str:
    """Normalize an identifier to a comparable form (DOI case, arXiv version...)."""
    normalized = str(value or "").strip()
    if field == "doi":
        normalized = re.sub(
            r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        return normalized.rstrip(". ").casefold()
    if field == "pmid":
        return re.sub(r"^pmid:\s*", "", normalized, flags=re.IGNORECASE)
    if field == "pmcid":
        return re.sub(r"^pmcid:\s*", "", normalized, flags=re.IGNORECASE).upper()
    if field == "arxiv_id":
        normalized = re.sub(
            r"^https?://arxiv\.org/(?:abs|pdf)/",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        return re.sub(r"v\d+$", "", normalized.removesuffix(".pdf"))
    if field == "openalex_id":
        return re.sub(
            r"^https?://openalex\.org/", "", normalized, flags=re.IGNORECASE
        ).upper()
    return normalized


def _values_match(field: str, expected: Any, actual: Any) -> bool:
    if field == "authors":
        return _authors_match(expected, actual)
    if field == "year":
        return _year_value(expected) == _year_value(actual)
    if field in IDENTIFIER_FIELDS:
        return canonical_identifier(field, expected) == canonical_identifier(field, actual)
    return normalize_text(expected) == normalize_text(actual)


def _authors_match(expected: Any, actual: Any) -> bool:
    """Prefix match: the expected author list must be the start of the actual one."""
    expected_names = _author_names(expected)
    actual_names = _author_names(actual)
    if not expected_names or not actual_names or len(expected_names) > len(actual_names):
        return False
    return expected_names == actual_names[: len(expected_names)]


def _author_names(value: Any) -> list[str]:
    values = (
        value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes))
        else [value]
    )
    names: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            item = item.get("name") or item.get("full_name") or item.get("family") or ""
        normalized = normalize_text(item)
        if normalized:
            names.append(normalized)
    return names


def _year_value(value: Any) -> int | None:
    try:
        return int(str(value).strip()[:4])
    except (TypeError, ValueError):
        return None


def normalize_text(value: Any) -> str:
    """NFKC + casefold, keeping only alphanumerics and spaces."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum() or char.isspace()).strip()
