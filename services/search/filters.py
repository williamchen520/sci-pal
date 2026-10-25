"""Three-stage filter handling: normalize -> translate -> post-filter.

Why three stages:

- ``normalize_filters`` decides what a filter *means* once (validated vocabulary),
  so every caller agrees on date formats and language codes.
- ``translate_filters`` turns that meaning into source-specific kwargs or query
  fragments, and records which fields the source cannot push down.
- ``apply_post_filters`` enforces the same meaning locally for records the source
  returned anyway (APIs routinely ignore or partially support filters).

Adapted from ``nature-academic-search`` (MIT, wp-a) ``filters.py``; the source
dialects are rewritten for SciPal's three retrieval paths (local / pubmed / openalex).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

FILTER_FIELDS = frozenset(
    {"date_from", "date_to", "language", "author", "document_type", "identifiers"}
)

DATE_FIELDS = ("date_from", "date_to")

#: Sources with a known dialect. Anything else gets "post-filter everything".
SOURCE_DIALECTS = frozenset({"local", "pubmed", "openalex"})

#: ISO 639-1 aliases (three-letter codes we meet in bibliographic records).
LANGUAGE_ALIASES = {
    "eng": "en",
    "chi": "zh",
    "zho": "zh",
    "ger": "de",
    "deu": "de",
    "fre": "fr",
    "fra": "fr",
    "spa": "es",
    "jpn": "ja",
    "rus": "ru",
    "por": "pt",
    "ita": "it",
    "kor": "ko",
}

_IDENTIFIER_FIELDS = ("doi", "pmid", "pmcid", "arxiv_id", "openalex_id")


def normalize_filters(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate and canonicalize the public filter object.

    Raises ``ValueError`` on unknown fields or malformed values — silent drops
    are how "I filtered by 2024" turns into "the filter did nothing".
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("filters must be an object")

    unknown = sorted(set(raw) - FILTER_FIELDS)
    if unknown:
        raise ValueError(f"Unknown filter field(s): {', '.join(unknown)}")

    normalized: dict[str, Any] = {}
    for field in DATE_FIELDS:
        value = raw.get(field)
        if value not in (None, ""):
            normalized[field] = _parse_date(value, field)
    if normalized.get("date_from") and normalized.get("date_to"):
        if normalized["date_from"] > normalized["date_to"]:
            raise ValueError("date_from must be on or before date_to")

    language = raw.get("language")
    if language not in (None, ""):
        code = str(language).strip().casefold()
        if not re.fullmatch(r"[a-z]{2,3}", code):
            raise ValueError("language must be a two- or three-letter code")
        normalized["language"] = LANGUAGE_ALIASES.get(code, code)

    author = raw.get("author")
    if author not in (None, ""):
        text = str(author).strip()
        if not text:
            raise ValueError("author must not be empty")
        normalized["author"] = text

    document_type = raw.get("document_type")
    if document_type not in (None, "", []):
        normalized["document_type"] = _string_list(document_type, "document_type")

    identifiers = raw.get("identifiers")
    if identifiers not in (None, "", []):
        normalized["identifiers"] = list(
            dict.fromkeys(
                _normalize_identifier(value)
                for value in _string_list(identifiers, "identifiers")
            )
        )

    return normalized


def translate_filters(source: str, filters: Mapping[str, Any]) -> dict[str, Any]:
    """Translate normalized filters into source-specific kwargs / query text.

    Returns ``{"kwargs", "query", "applied", "post_filter"}``. ``post_filter``
    lists the fields the source cannot handle, so the caller knows what must be
    checked locally after retrieval.
    """
    normalized = normalize_filters(filters)
    kwargs: dict[str, Any] = {}
    query_parts: list[str] = []
    applied: list[str] = []
    post_filter: list[str] = []

    if source == "pubmed":
        if "date_from" in normalized or "date_to" in normalized:
            start = normalized.get("date_from", "0000-01-01").replace("-", "/")
            end = normalized.get("date_to", "3000-12-31").replace("-", "/")
            query_parts.append(
                f'("{start}"[Date - Publication] : "{end}"[Date - Publication])'
            )
            applied.extend(field for field in DATE_FIELDS if field in normalized)
        if "author" in normalized:
            query_parts.append(f'{normalized["author"]}[Author]')
            applied.append("author")
        if "language" in normalized:
            query_parts.append(f'{normalized["language"]}[Language]')
            applied.append("language")
        if "document_type" in normalized:
            query_parts.append(
                " OR ".join(
                    f'"{value}"[Publication Type]'
                    for value in normalized["document_type"]
                )
            )
            applied.append("document_type")
        if "identifiers" in normalized:
            post_filter.append("identifiers")

    elif source == "openalex":
        for field in ("date_from", "date_to", "language", "author"):
            if field in normalized:
                kwargs[field] = normalized[field]
                applied.append(field)
        if "document_type" in normalized:
            kwargs["document_type"] = normalized["document_type"]
            applied.append("document_type")
        if "identifiers" in normalized:
            post_filter.append("identifiers")

    elif source == "local":
        # The retriever does not accept filter arguments yet; keep the contract
        # honest instead of pretending a pushdown happened.
        post_filter.extend(normalized)

    else:
        post_filter.extend(normalized)

    return {
        "kwargs": kwargs,
        "query": " AND ".join(query_parts),
        "applied": list(dict.fromkeys(applied)),
        "post_filter": list(dict.fromkeys(post_filter)),
    }


def apply_post_filters(
    records: Sequence[Mapping[str, Any]],
    filters: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Strict local filtering for fields a source may ignore or omit.

    Missing values fail the filter (strict) so a "2020-2024" query cannot be
    silently satisfied by undated records.
    """
    normalized = normalize_filters(filters)
    if not normalized:
        return [dict(record) for record in records]
    return [dict(record) for record in records if _matches(record, normalized)]


def _matches(record: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    if "date_from" in filters or "date_to" in filters:
        candidate = _record_date(record)
        if candidate is None:
            return False
        if filters.get("date_from") and candidate < filters["date_from"]:
            return False
        if filters.get("date_to") and candidate > filters["date_to"]:
            return False

    if "language" in filters:
        value = record.get("language") or record.get("lang")
        code = str(value or "").strip().casefold()
        if not code:
            return False
        if LANGUAGE_ALIASES.get(code, code) != filters["language"]:
            return False

    if "author" in filters:
        needle = _normalize_token(filters["author"])
        haystack = " ".join(
            _author_names(record.get("authors") or record.get("author"))
        )
        if needle not in haystack:
            return False

    if "document_type" in filters:
        value = record.get("document_type") or record.get("type") or record.get("publication_type")
        if not value:
            return False
        values = value if isinstance(value, (list, tuple)) else [value]
        available = {_normalize_token(item) for item in values}
        wanted = {_normalize_token(item) for item in filters["document_type"]}
        if not (available & wanted):
            return False

    if "identifiers" in filters:
        available = {
            _normalize_identifier(record[field])
            for field in _IDENTIFIER_FIELDS
            if record.get(field)
        }
        if not (available & set(filters["identifiers"])):
            return False

    return True


def _parse_date(value: Any, field: str) -> str:
    """Accept YYYY / YYYY-MM / YYYY-MM-DD and return YYYY-MM-DD."""
    text = str(value).strip()
    parts = text.split("-")
    if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        raise ValueError(f"{field} must be YYYY, YYYY-MM or YYYY-MM-DD")
    year = parts[0]
    if len(year) != 4:
        raise ValueError(f"{field} must start with a four-digit year")
    month = parts[1] if len(parts) > 1 else "01"
    day = parts[2] if len(parts) > 2 else "01"
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid date: {text}") from exc


def _record_date(record: Mapping[str, Any]) -> str | None:
    value = record.get("publication_date") or record.get("date") or record.get("year")
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 4 and text.isdigit():
        return f"{text}-01-01"
    if len(text) == 7:
        return f"{text}-01"
    return text[:10]


def _string_list(value: Any, field: str) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else [value]
    items = [str(item).strip() for item in values if str(item).strip()]
    if not items:
        raise ValueError(f"{field} must not be empty")
    return list(dict.fromkeys(items))


def _normalize_identifier(value: Any) -> str:
    text = str(value).strip()
    lowered = text.casefold()
    if lowered.startswith("doi:") or "doi.org/" in lowered or text.startswith("10."):
        return re.sub(
            r"^(?:doi:\s*|https?://(?:dx\.)?doi\.org/)", "", text, flags=re.IGNORECASE
        ).rstrip(". ").casefold()
    if lowered.startswith("pmid:"):
        return re.sub(r"^pmid:\s*", "", text, flags=re.IGNORECASE)
    if lowered.startswith("pmcid:"):
        return re.sub(r"^pmcid:\s*", "", text, flags=re.IGNORECASE).upper()
    if "arxiv.org/" in lowered:
        stripped = re.sub(
            r"^https?://arxiv\.org/(?:abs|pdf)/", "", text, flags=re.IGNORECASE
        ).removesuffix(".pdf")
        return re.sub(r"v\d+$", "", stripped)
    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", text):
        return re.sub(r"v\d+$", "", text)
    return text.casefold()


def _author_names(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else [value]
    names: list[str] = []
    for item in values:
        if isinstance(item, Mapping):
            item = item.get("name") or item.get("full_name") or item.get("family") or ""
        normalized = _normalize_token(item)
        if normalized:
            names.append(normalized)
    return names


def _normalize_token(value: Any) -> str:
    """Lowercase and turn punctuation into spaces (for names and type labels)."""
    text = re.sub(r"[^\w]+", " ", str(value or "").casefold(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()
