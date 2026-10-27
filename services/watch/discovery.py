"""Journal discovery (OpenAlex) and candidate search (Crossref)."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from services.watch import repo

USER_AGENT = "SciPal-Watch/1.0 (mailto:scipal@example.org)"
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org/works"


def _get_json(url: str, timeout: int = 30) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def openalex_sources(
    field_text: str = "",
    topic_ids: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    params = {"per-page": min(limit, 100), "sort": "cited_by_count:desc"}
    if topic_ids:
        params["filter"] = "topics.id:" + "|".join(topic_ids[:5])
    elif field_text:
        params["search"] = field_text
    else:
        return []
    candidates = [field_text]
    words = (field_text or "").split()
    if len(words) > 4:
        candidates.append(" ".join(words[:4]))
    if len(words) > 2:
        candidates.append(" ".join(words[:2]))
    data = {}
    for term in candidates:
        params.pop("search", None)
        if term:
            params["search"] = term
        data = _get_json(f"{OPENALEX}/sources?" + urllib.parse.urlencode(params))
        if data.get("results"):
            break
    out = []
    for item in data.get("results") or []:
        stats = item.get("summary_stats") or {}
        metric = stats.get("2yr_mean_citedness") or stats.get("2yr_mean_citedness_score")
        out.append(
            {
                "issn_l": item.get("issn_l") or (item.get("issn") or [None])[0],
                "name": item.get("display_name"),
                "openalex_source_id": (item.get("id") or "").rsplit("/", 1)[-1],
                "sjr": None,
                "sjr_quartile": None,
                "metric_year": 2024,
                "works_count": item.get("works_count"),
                "openalex_metric": metric,
                "topics": [t.get("display_name") for t in item.get("topics") or []][:3],
            }
        )
    return [item for item in out if item["issn_l"]]


def openalex_topic_search(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    candidates = [query]
    words = (query or "").split()
    if len(words) > 4:
        candidates.append(" ".join(words[:4]))
    if len(words) > 2:
        candidates.append(" ".join(words[:2]))
    data = {}
    for term in candidates:
        data = _get_json(
            f"{OPENALEX}/topics?"
            + urllib.parse.urlencode({"search": term, "per-page": min(limit, 25)})
        )
        if data.get("results"):
            break
    return [
        {
            "id": (item.get("id") or "").rsplit("/", 1)[-1],
            "name": item.get("display_name"),
            "works_count": item.get("works_count"),
        }
        for item in data.get("results") or []
    ]


def discover_journals(conn, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Union auto-discovered top journals with manually pinned ISSNs."""
    profile_id = profile["id"]
    existing = {row["issn_l"]: row for row in repo.list_journals(conn, profile_id)}
    manual = {
        issn: entry
        for issn, entry in existing.items()
        if entry.get("source") in ("manual", "exclude")
    }
    auto = []
    if profile.get("field_text") or profile.get("openalex_topic_ids"):
        topic_ids = profile.get("openalex_topic_ids")
        if isinstance(topic_ids, str):
            try:
                topic_ids = json.loads(topic_ids)
            except json.JSONDecodeError:
                topic_ids = []
        sources = openalex_sources(
            profile.get("field_text") or "",
            topic_ids or [],
            limit=max(profile.get("top_journal_count") or 30, 1) * 2,
        )
        sources.sort(
            key=lambda item: item.get("openalex_metric") or item.get("works_count") or 0,
            reverse=True,
        )
        auto = sources[: int(profile.get("top_journal_count") or 30)]
        allowed = {entry.get("issn_l") for entry in auto}
        if profile.get("metric_min"):
            auto = [
                entry
                for entry in auto
                if (entry.get("openalex_metric") or 0) >= float(profile["metric_min"])
            ]
        for entry in auto:
            repo.upsert_journal(
                conn,
                {
                    "issn_l": entry["issn_l"],
                    "name": entry.get("name"),
                    "openalex_source_id": entry.get("openalex_source_id"),
                    "works_count": entry.get("works_count"),
                    "metric_year": 2024,
                },
            )
        # drop previously auto-added ISSNs that no longer make the cut
        for issn in list(existing):
            if existing[issn].get("source") == "auto" and issn not in allowed:
                conn.execute(
                    "DELETE FROM watch_profile_journals WHERE profile_id = ? AND issn_l = ?",
                    (profile_id, issn),
                )
    merged = {entry["issn_l"]: {**entry, "source": entry.get("source", "auto")} for entry in auto}
    merged.update(manual)
    repo.set_journals(
        conn,
        profile_id,
        [
            {"issn_l": issn, "name": entry.get("name"), "source": entry.get("source", "auto")}
            for issn, entry in merged.items()
        ],
    )
    conn.commit()
    return repo.list_journals(conn, profile_id)


def _crossref_date(item: Dict[str, Any]) -> str:
    for key in ("published", "issued", "published-print", "published-online"):
        parts = ((item.get(key) or {}).get("date-parts") or [[None]])[0]
        if parts and parts[0]:
            return "-".join(f"{int(p):02d}" if i else str(p) for i, p in enumerate(parts[:3]))
    return ""


def crossref_candidates(
    issns: List[str],
    date_from: str,
    date_to: str,
    query: str = "",
    rows: int = 100,
) -> List[Dict[str, Any]]:
    filters = [
        f"from-pub-date:{date_from}",
        f"until-pub-date:{date_to}",
        "type:journal-article",
    ]
    base_params = {
        "filter": ",".join(filters),
        "rows": min(rows, 100),
        "sort": "published",
        "order": "desc",
        "select": "DOI,title,abstract,container-title,ISSN,published,issued,author",
    }
    if query:
        base_params["query.bibliographic"] = query
    out: List[Dict[str, Any]] = []
    seen = set()
    targets = issns[:30] if issns else [None]
    for issn in targets:
        if issn:
            url = (
                f"https://api.crossref.org/journals/{urllib.parse.quote(issn)}/works?"
                + urllib.parse.urlencode(base_params)
            )
        else:
            url = f"{CROSSREF}?" + urllib.parse.urlencode(base_params)
        data = _get_json(url, timeout=45)
        for item in (data.get("message") or {}).get("items") or []:
            doi = (item.get("DOI") or "").lower()
            if not doi or doi in seen:
                continue
            seen.add(doi)
            out.append(
                {
                    "doi": doi,
                    "title": _clean((item.get("title") or [""])[0]),
                    "abstract": _clean(item.get("abstract") or ""),
                    "journal": (item.get("container-title") or [""])[0],
                    "issn_l": (item.get("ISSN") or [None])[0],
                    "published": _crossref_date(item),
                    "authors": [
                        f"{a.get('given', '')} {a.get('family', '')}".strip()
                        for a in item.get("author") or []
                    ],
                    "url": item.get("URL"),
                }
            )
    return out
