"""Retraction / correction flags from OpenAlex and Crossref."""

from __future__ import annotations

import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

OPENALEX = "https://api.openalex.org/works/https://doi.org/"
CROSSREF = "https://api.crossref.org/works/"
USER_AGENT = "SciPal-Trust/1.0"


def _get_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def check_doi(doi: str, get_json: Optional[Callable[[str], Dict[str, Any]]] = None) -> List[Dict]:
    """Return flags found for one DOI (best effort, no exceptions)."""
    getter = get_json or _get_json
    flags: List[Dict] = []
    clean = doi.strip().lower().replace("https://doi.org/", "")
    if not clean:
        return flags

    try:
        data = getter(OPENALEX + urllib.parse.quote(clean))
        if data.get("is_retracted"):
            flags.append(
                {
                    "flag_type": "retracted",
                    "source": "openalex",
                    "detail": data.get("id") or "",
                }
            )
    except Exception:  # noqa: BLE001
        pass

    try:
        data = getter(CROSSREF + urllib.parse.quote(clean))
        message = data.get("message") or {}
        for update in message.get("update-to") or []:
            kind = (update.get("type") or "").lower()
            if kind in ("retraction", "correction", "expression_of_concern"):
                flags.append(
                    {
                        "flag_type": kind,
                        "source": "crossref",
                        "detail": update.get("DOI") or "",
                    }
                )
    except Exception:  # noqa: BLE001
        pass
    return flags


def flag_paper(
    conn: sqlite3.Connection,
    paper_id: str,
    flags: List[Dict],
) -> int:
    inserted = 0
    for flag in flags:
        conn.execute(
            "INSERT OR REPLACE INTO paper_flags "
            "(paper_id, flag_type, source, detail, checked_at) VALUES (?, ?, ?, ?, ?)",
            (
                paper_id,
                flag["flag_type"],
                flag["source"],
                flag.get("detail", ""),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        inserted += 1
    conn.commit()
    return inserted


def flags_for_papers(conn: sqlite3.Connection, paper_ids: List[str]) -> Dict[str, List[Dict]]:
    if not paper_ids:
        return {}
    marks = ",".join("?" * len(paper_ids))
    rows = conn.execute(
        f"SELECT paper_id, flag_type, source, detail FROM paper_flags "
        f"WHERE paper_id IN ({marks})",
        paper_ids,
    ).fetchall()
    out: Dict[str, List[Dict]] = {}
    for paper_id, flag_type, source, detail in rows:
        out.setdefault(paper_id, []).append(
            {"flag_type": flag_type, "source": source, "detail": detail}
        )
    return out
