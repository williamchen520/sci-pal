"""Stable identities for records and quotes.

Two problems this solves:

1. **Record identity** — the same paper arrives from several sources (local DB, PMC,
   PubMed, OpenAlex) under different spellings. ``stable_record_id`` gives one
   deterministic key so merges and de-duplication do not depend on dict order.
2. **Quote anchoring** — paragraph ids are regenerated when a PDF/XML is re-parsed,
   which silently breaks every stored citation. ``quote_hash`` fingerprints the text
   itself, so an anchor can be re-matched after a rebuild instead of disappearing.

Adapted from ``nature-academic-search`` (MIT, wp-a) ``provenance.py``;
the quote-anchor part is new (the upstream project has no full text).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

#: (field, namespace) in priority order. First non-empty wins.
STRONG_IDENTIFIERS: tuple[tuple[str, str], ...] = (
    ("doi", "doi"),
    ("pmid", "pmid"),
    ("pmcid", "pmcid"),
    ("arxiv_id", "arxiv"),
    ("openalex_id", "openalex"),
    ("semantic_scholar_id", "semantic_scholar"),
    ("nct_id", "nct"),
)

_ANCHOR_SCHEMA = "1"


def stable_record_id(record: Mapping[str, Any], *, entity_type: str | None = None) -> str:
    """Return a deterministic, namespaced id for a normalized record.

    Falls back to a content hash of ``title + year + first author`` when no
    strong identifier is present. The fallback is stable across case,
    punctuation and whitespace differences.
    """
    entity = _normalize_token(entity_type or record.get("entity_type") or "paper")

    for field, namespace in STRONG_IDENTIFIERS:
        value = canonical_identifier(field, record.get(field))
        if value:
            return f"{entity}:{namespace}:{value}"

    fallback = "\x1f".join(
        (
            entity,
            normalize_text(record.get("title")),
            _year(record.get("year")),
            normalize_text(_first_author(record)),
        )
    )
    digest = hashlib.sha256(fallback.encode("utf-8")).hexdigest()[:24]
    return f"{entity}:sha256:{digest}"


def result_fingerprint(record_ids: Sequence[str]) -> str:
    """Hash an ordered list of record ids so two result sets can be compared."""
    payload = "\n".join(str(record_id) for record_id in record_ids)
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def normalize_quote(text: Any) -> str:
    """Normalize quote text before hashing.

    Punctuation becomes a space (not nothing), so ``1.2M`` and ``1 2M`` converge
    while ``12M`` and ``1.2M`` stay different. Layout noise from re-parsing
    (extra spaces, line breaks, hyphenation) is therefore ignored.
    """
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def quote_hash(text: Any) -> str:
    """Fingerprint a quotation so it can be re-found after a re-parse."""
    normalized = normalize_quote(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"sha256:{digest}"


def make_anchor(para_id: str | int | None, text: Any) -> dict[str, Any]:
    """Build a citation anchor: a paragraph id plus a text fingerprint."""
    return {
        "schema_version": _ANCHOR_SCHEMA,
        "para_id": para_id,
        "quote_hash": quote_hash(text),
    }


def anchor_matches(anchor: Mapping[str, Any], text: Any) -> bool:
    """True when ``text`` still equals the text the anchor was built from."""
    expected = str(anchor.get("quote_hash") or "")
    return bool(expected) and expected == quote_hash(text)


def canonical_identifier(field: str, value: Any) -> str:
    """Normalize an identifier to its comparable form."""
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
    if field == "nct_id":
        return normalized.upper()
    return normalized


def normalize_text(value: Any) -> str:
    """NFKC + casefold, keeping only alphanumerics and spaces."""
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum() or char.isspace()).strip()


def _first_author(record: Mapping[str, Any]) -> Any:
    authors = record.get("authors")
    if isinstance(authors, Sequence) and not isinstance(authors, (str, bytes)) and authors:
        first = authors[0]
        if isinstance(first, Mapping):
            return first.get("name") or first.get("full_name") or first.get("family") or ""
        return first
    return record.get("first_author") or ""


def _year(value: Any) -> str:
    try:
        return str(int(str(value).strip()[:4]))
    except (TypeError, ValueError):
        return ""


def _normalize_token(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()
