"""Watch run: window -> search -> dedup -> score -> select -> ingest -> digest."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from services.watch import discovery, repo

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
_STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "into", "their", "have", "has", "not", "but", "use", "using", "study",
}


def _tokens(text: str) -> List[str]:
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if len(t) > 2 and t.lower() not in _STOP
    ]


def _overlap(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    return len(set(a) & set(b)) / max(len(set(a)), 1)


def _recency(published: str, now: datetime) -> float:
    if not published:
        return 0.0
    try:
        date = datetime.fromisoformat(published[:10])
    except ValueError:
        return 0.0
    days = max((now.date() - date.date()).days, 0)
    return max(0.0, 1.0 - days / 30.0)


def _metric_score(metric: Optional[float], values: List[float]) -> float:
    if not values or metric is None:
        return 0.0
    hi = max(values) or 1.0
    return max(0.0, min(1.0, metric / hi))


def _paper_id(doi: str, title: str) -> str:
    seed = doi or title
    return "paper_watch_" + hashlib.sha1(seed.encode()).hexdigest()[:12]


def ingest_abstract(conn, candidate: Dict[str, Any]) -> str:
    """Store metadata + abstract only (acquisition='abstract')."""
    paper_id = _paper_id(candidate.get("doi") or "", candidate.get("title") or "")
    conn.execute(
        "INSERT OR IGNORE INTO papers "
        "(paper_id, filename, title, authors, abstract, journal, year, doi, parse_status, "
        "parse_engine, acquisition, created_at, updated_at) "
        "VALUES (?, '', ?, ?, ?, ?, ?, ?, 'abstract', 'watch', 'abstract', ?, ?)",
        (
            paper_id,
            candidate.get("title"),
            json.dumps(candidate.get("authors") or [], ensure_ascii=False),
            candidate.get("abstract") or "",
            candidate.get("journal"),
            (candidate.get("published") or "")[:4] or None,
            candidate.get("doi"),
            repo.now_iso(),
            repo.now_iso(),
        ),
    )
    conn.commit()
    return paper_id


def _digest(profile: Dict[str, Any], run: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    lines = [
        f"【文献监测】{profile['name']} · {run['window_end'][:10]}",
        f"候选 {run['found']}，入选 {run['selected']}"
        f"（同刊限 {profile.get('same_journal_limit') or 2}），"
        f"新增全文 {run['imported_full']} / 摘要 {run['imported_abstract']}",
        "",
    ]
    for index, item in enumerate(items, 1):
        tag = "全文" if item.get("acquisition") == "fulltext" else "仅摘要"
        lines.append(
            f"{index}. {item['title']}｜{item.get('journal') or ''}｜"
            f"{item.get('published') or ''}｜{tag}"
        )
        if item.get("reason"):
            lines.append(f"   为什么选：{item['reason']}")
        abstract = item.get("abstract") or ""
        if abstract:
            lines.append(f"   摘要：{abstract[:280]}")
        if item.get("doi"):
            lines.append(f"   DOI: {item['doi']}")
        lines.append("")
    lines.append(f"全部：/watch.html?profile={profile['id']}&run={run['id']}")
    return "\n".join(lines)


def try_fulltext(db_path, conn, candidate: Dict[str, Any], abstract_paper_id: str):
    """Try Europe PMC OA JATS; on success replace the abstract-only record."""
    doi = candidate.get("doi")
    if not doi:
        return None
    try:
        from services.search.europe_pmc import EuropePMCClient

        client = EuropePMCClient(timeout=20)
        hits = client.search(f'DOI:"{doi}"', page_size=3)
        pmcid = next((h.get("pmcid") for h in hits if h.get("pmcid")), None)
        if not pmcid:
            return None
        full_id = f"paper_watch_{pmcid.lower()}"
        conn.execute(
            "INSERT OR IGNORE INTO papers "
            "(paper_id, filename, title, doi, parse_status, acquisition) "
            "VALUES (?, ?, ?, ?, 'pending', 'abstract')",
            (full_id, f"{pmcid.upper()}.xml", candidate.get("title"), doi),
        )
        conn.commit()
        result = client.download_and_import(pmcid, db_path=db_path)
        if result.get("status") != "imported":
            return None
        conn.execute("DELETE FROM papers WHERE paper_id = ?", (abstract_paper_id,))
        conn.commit()
        return full_id
    except Exception:  # noqa: BLE001 - OA lookup must never break a watch run
        return None


def _heartbeat_digest(profile: Dict[str, Any], found: int, journals: int) -> str:
    return (
        f"【文献监测】{profile['name']} · 本月无新增\n"
        f"候选 {found}，期刊 {journals}；"
        f"下次 {int(profile.get('interval_days') or 3)} 天后继续。"
    )


def try_oa_pdf(db_path, conn, candidate: Dict[str, Any], abstract_paper_id: str):
    """Unpaywall OA PDF fallback; requires SCIPAL_UNPAYWALL_EMAIL."""
    import json as _json
    import os
    import re as _re
    import urllib.parse
    import urllib.request

    doi = candidate.get("doi")
    email = os.environ.get("SCIPAL_UNPAYWALL_EMAIL")
    if not doi or not email:
        return None
    try:
        url = (
            f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?"
            + urllib.parse.urlencode({"email": email})
        )
        with urllib.request.urlopen(url, timeout=25) as response:
            data = _json.loads(response.read().decode())
        location = data.get("best_oa_location") or {}
        pdf_url = location.get("url_for_pdf") or location.get("url")
        if not pdf_url:
            return None
        from services.search.preprint_ingest import ingest_pdf

        filename = _re.sub(r"[^A-Za-z0-9]+", "_", doi)[:80] + ".pdf"
        result = ingest_pdf(
            pdf_url, filename, candidate, db_path=db_path, parse=True
        )
        paper_id = result.get("paper_id") or (result.get("stats") or {}).get("paper_id")
        if not paper_id:
            return None
        conn.execute("DELETE FROM papers WHERE paper_id = ?", (abstract_paper_id,))
        conn.commit()
        return paper_id
    except Exception:  # noqa: BLE001
        return None


def run_profile(
    db_path,
    profile_id: int,
    now: Optional[datetime] = None,
    candidate_fn=None,
    fulltext_fn=None,
    oa_pdf_fn=None,
) -> Dict[str, Any]:
    conn = repo.connect(db_path)
    profile = repo.get_profile(conn, profile_id)
    if not profile:
        raise ValueError("profile not found")
    now = now or datetime.now(timezone.utc)
    window_days = max(int(profile.get("window_days") or 7), int(profile.get("interval_days") or 3))
    start = now - timedelta(days=window_days)
    owner = profile.get("owner") or "default"
    run_id = repo.create_run(
        conn, profile_id, start.isoformat(), now.isoformat(), owner=owner
    )
    stats = {"found": 0, "selected": 0, "imported_full": 0, "imported_abstract": 0, "skipped": 0}
    try:
        journals = repo.list_journals(conn, profile_id)
        if not journals and (profile.get("field_text") or profile.get("openalex_topic_ids")):
            journals = discovery.discover_journals(conn, profile)
        issns = [row["issn_l"] for row in journals if row.get("issn_l")]
        metrics = repo.journal_metrics(conn, issns)
        search = candidate_fn or discovery.crossref_candidates
        candidates = search(
            issns,
            start.date().isoformat(),
            now.date().isoformat(),
            query=" ".join(
                filter(None, [profile.get("field_text"), profile.get("keywords")])
            )[:300],
            rows=100,
        )
        stats["found"] = len(candidates)

        field_tokens = _tokens(" ".join(filter(None, [profile.get("field_text"), profile.get("keywords")])))
        keyword_tokens = _tokens(profile.get("keywords") or "")
        metric_values = [
            row.get("sjr") or 0.0 for row in metrics.values() if (row.get("sjr") or 0.0) > 0
        ]
        scored = []
        for candidate in candidates:
            key = repo.dedup_key(candidate.get("doi"), candidate.get("title"))
            if repo.seen(conn, profile_id, key) or repo.paper_exists(conn, candidate.get("doi")):
                stats["skipped"] += 1
                continue
            title_abstract = f"{candidate.get('title', '')} {candidate.get('abstract', '')}"
            overlap = _overlap(field_tokens, _tokens(title_abstract))
            keyword_hit = _overlap(keyword_tokens, _tokens(title_abstract))
            metric = (metrics.get(candidate.get("issn_l") or "") or {}).get("sjr") or 0.0
            score = (
                0.45 * overlap
                + 0.20 * keyword_hit
                + 0.15 * _metric_score(metric, metric_values)
                + 0.20 * _recency(candidate.get("published") or "", now)
            )
            scored.append((score, candidate))
        scored.sort(key=lambda pair: pair[0], reverse=True)

        selected: List[Dict[str, Any]] = []
        per_journal: Dict[str, int] = {}
        limit = int(profile.get("max_items") or 3)
        same_limit = int(profile.get("same_journal_limit") or 2)
        relaxed = False
        for position, (score, candidate) in enumerate(scored):
            if len(selected) >= limit:
                break
            journal = candidate.get("journal") or candidate.get("issn_l") or "?"
            if per_journal.get(journal, 0) >= same_limit:
                remaining = {
                    (c.get("journal") or c.get("issn_l") or "?")
                    for _, c in scored[position + 1:]
                }
                if len(scored) <= limit and len(selected) < limit:
                    relaxed = True
                else:
                    continue
            per_journal[journal] = per_journal.get(journal, 0) + 1
            selected.append({"score": score, **candidate})

        items = []
        fulltext_fn = fulltext_fn or try_fulltext
        for candidate in selected:
            paper_id = ingest_abstract(conn, candidate)
            acquisition = "abstract"
            full_paper_id = fulltext_fn(db_path, conn, candidate, paper_id)
            if not full_paper_id:
                oa_pdf_fn = oa_pdf_fn or try_oa_pdf
                full_paper_id = oa_pdf_fn(db_path, conn, candidate, paper_id)
            if full_paper_id:
                paper_id = full_paper_id
                acquisition = "fulltext"
            key = repo.dedup_key(candidate.get("doi"), candidate.get("title"))
            repo.mark_seen(conn, profile_id, key, paper_id)
            reason = (
                f"领域匹配 {candidate['score']:.2f}；"
                f"{candidate.get('journal') or '未知期刊'}；{candidate.get('published') or '日期未知'}"
            )
            item = {
                "paper_id": paper_id,
                "doi": candidate.get("doi"),
                "title": candidate.get("title"),
                "journal": candidate.get("journal"),
                "published": candidate.get("published"),
                "score": candidate["score"],
                "reason": reason,
                "acquisition": acquisition,
                "owner": owner,
                "abstract": candidate.get("abstract") or "",
            }
            repo.add_item(conn, run_id, profile_id, item)
            items.append(item)
            if acquisition == "fulltext":
                stats["imported_full"] += 1
            else:
                stats["imported_abstract"] += 1
        stats["selected"] = len(items)

        run = repo.get_run(conn, run_id)
        run = {**run, **stats}
        heartbeat = 0
        pushed = False
        if items:
            digest = _digest(profile, run, items)
            pushed = True
        else:
            stamps = [
                value
                for value in (profile.get("last_push_at"), profile.get("last_heartbeat_at"))
                if value
            ]
            last_push = max(stamps) if stamps else None
            due = True
            if last_push:
                try:
                    due = (now - datetime.fromisoformat(last_push)).days >= 30
                except ValueError:
                    due = True
            if due:
                digest = _heartbeat_digest(profile, stats["found"], len(journals))
                heartbeat = 1
                pushed = True
            else:
                digest = ""
        repo.finish_run(
            conn,
            run_id,
            status="success" if items else "empty",
            digest_md=digest,
            heartbeat=heartbeat,
            **stats,
        )
        conn.execute(
            "UPDATE watch_profiles SET last_run_at = ?, next_run_at = ? WHERE id = ?",
            (
                now.isoformat(),
                (now + timedelta(days=int(profile.get("interval_days") or 3))).isoformat(),
                profile_id,
            ),
        )
        if pushed:
            if heartbeat:
                conn.execute(
                    "UPDATE watch_profiles SET last_push_at = ?, last_heartbeat_at = ? WHERE id = ?",
                    (now.isoformat(), now.isoformat(), profile_id),
                )
            else:
                conn.execute(
                    "UPDATE watch_profiles SET last_push_at = ? WHERE id = ?",
                    (now.isoformat(), profile_id),
                )
        conn.commit()
        return {
            "run_id": run_id,
            "profile_id": profile_id,
            "digest": digest,
            "heartbeat": bool(heartbeat),
            **stats,
        }
    except Exception as exc:  # noqa: BLE001
        repo.finish_run(conn, run_id, status="failed", error=str(exc)[:500], **stats)
        raise
    finally:
        conn.close()
