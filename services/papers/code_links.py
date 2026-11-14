"""Paper code-link extraction and manual registration."""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlparse

from services.db.pg_pool import corpus_connection, owner_connection

URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|zenodo\.org|doi\.org/10\.5281)"
    r"/[^\s<>\"')\]]+",
    re.IGNORECASE,
)
_TRAILING = ".,;:"
_ALLOWED_HOSTS = {
    "github.com",
    "www.github.com",
    "gitlab.com",
    "www.gitlab.com",
    "bitbucket.org",
    "www.bitbucket.org",
    "zenodo.org",
    "www.zenodo.org",
    "doi.org",
}


def _clean(url: str) -> str:
    return url.strip().rstrip(_TRAILING)


def _repo_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "github" in host:
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if "bitbucket" in host:
        return "bitbucket"
    if "zenodo" in host or "doi.org" in host:
        return "zenodo"
    return "unknown"


def link_id(paper_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{paper_id}\0{url}".encode("utf-8")).hexdigest()[:16]
    return f"link_{digest}"


def extract_candidates(paper_id: str) -> list[dict[str, Any]]:
    pg = corpus_connection()
    try:
        rows = pg.execute(
            "SELECT para_id, text FROM paragraphs WHERE paper_id=%s ORDER BY sequence",
            (paper_id,),
        ).fetchall()
    finally:
        pg.close()
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        for match in URL_RE.finditer(str(row["text"] or "")):
            url = _clean(match.group(0))
            if not url or url in found:
                continue
            found[url] = {
                "link_id": link_id(paper_id, url),
                "paper_id": paper_id,
                "url": url,
                "repo_type": _repo_type(url),
                "confidence": 0.6,
                "evidence_para_id": row["para_id"],
                "status": "candidate",
            }
    return list(found.values())


def _upsert(links: list[dict[str, Any]]) -> int:
    if not links:
        return 0
    pg = owner_connection()
    try:
        for link in links:
            pg.execute(
                """
                INSERT INTO paper_code_links
                  (link_id,paper_id,url,repo_type,license,commit_sha,confidence,evidence_para_id,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (paper_id,url) DO UPDATE SET
                  repo_type=EXCLUDED.repo_type,
                  confidence=GREATEST(paper_code_links.confidence, EXCLUDED.confidence),
                  evidence_para_id=COALESCE(paper_code_links.evidence_para_id, EXCLUDED.evidence_para_id),
                  updated_at=now()
                """,
                (
                    link["link_id"],
                    link["paper_id"],
                    link["url"],
                    link.get("repo_type") or "unknown",
                    link.get("license"),
                    link.get("commit_sha"),
                    float(link.get("confidence") or 0.5),
                    link.get("evidence_para_id"),
                    link.get("status") or "candidate",
                ),
            )
        pg.commit()
        return len(links)
    finally:
        pg.close()


def extract_and_store(paper_id: str) -> dict[str, Any]:
    candidates = extract_candidates(paper_id)
    count = _upsert(candidates)
    return {"paper_id": paper_id, "extracted": count, "links": candidates}


def manual_link(
    paper_id: str,
    url: str,
    *,
    license_value: str = "",
    commit_sha: str = "",
    status: str = "candidate",
) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in _ALLOWED_HOSTS:
        raise ValueError("url must be GitHub/GitLab/Bitbucket/Zenodo")
    if status not in {"candidate", "validated", "rejected"}:
        raise ValueError("invalid status")
    link = {
        "link_id": link_id(paper_id, url),
        "paper_id": paper_id,
        "url": url,
        "repo_type": _repo_type(url),
        "license": license_value or None,
        "commit_sha": commit_sha or None,
        "confidence": 1.0,
        "evidence_para_id": None,
        "status": status,
    }
    _upsert([link])
    return link


def list_links(paper_id: str) -> list[dict[str, Any]]:
    pg = corpus_connection()
    try:
        rows = pg.execute(
            "SELECT link_id,paper_id,url,repo_type,license,commit_sha,confidence,"
            "evidence_para_id,status,created_at,updated_at "
            "FROM paper_code_links WHERE paper_id=%s ORDER BY created_at",
            (paper_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()
