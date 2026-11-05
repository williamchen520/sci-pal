"""PostgreSQL WatchStore (G3.10f4 P1)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from services.db.pg_pool import pg_connection
from services.watch import pg_read, pg_writes
from services.watch.repo import now_iso


def connect(db_path=None):
    return None


def list_profiles(conn, owner: Optional[str] = None) -> List[Dict]:
    return pg_read.list_profiles(owner)


def get_profile(conn, profile_id: int, owner: Optional[str] = None) -> Optional[Dict]:
    return pg_read.get_profile(profile_id, owner)


def create_profile(conn, data: Dict[str, Any]) -> int:
    fields = [
        "owner", "name", "field_text", "keywords", "openalex_topic_ids", "interval_days",
        "window_days", "top_journal_count", "max_items", "same_journal_limit",
        "metric_type", "metric_min", "language", "delivery", "enabled",
    ]
    values = [data.get(f) for f in fields]
    if values[-1] is None:
        values[-1] = 1
    if isinstance(data.get("openalex_topic_ids"), (list, tuple)):
        values[4] = json.dumps(list(data["openalex_topic_ids"]))
    if not data.get("name"):
        raise ValueError("name required")
    payload = {field: values[index] for index, field in enumerate(fields)}
    payload["owner"] = data.get("owner") or "default"
    payload["created_at"] = now_iso()
    return pg_writes.create_profile(payload)


def update_profile(conn, profile_id: int, data: Dict[str, Any]) -> None:
    allowed = {
        "name", "field_text", "keywords", "openalex_topic_ids", "interval_days",
        "window_days", "top_journal_count", "max_items", "same_journal_limit",
        "metric_type", "metric_min", "language", "delivery", "enabled",
        "last_run_at", "next_run_at", "last_push_at", "last_heartbeat_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if "openalex_topic_ids" in updates and isinstance(updates["openalex_topic_ids"], (list, tuple)):
        updates["openalex_topic_ids"] = json.dumps(list(updates["openalex_topic_ids"]))
    if updates:
        pg_writes.update_profile(profile_id, updates)


def delete_profile(conn, profile_id: int) -> None:
    pg_writes.delete_profile(profile_id)


def list_journals(conn, profile_id: int) -> List[Dict]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM watch_profile_journals WHERE profile_id = %s ORDER BY issn_l",
            (profile_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def set_journals(conn, profile_id: int, entries: List[Dict]) -> None:
    pg_writes.replace_journals(profile_id, entries, now_iso())


def upsert_journal(conn, journal: Dict) -> None:
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO journal_catalog "
            "(issn_l, name, openalex_source_id, sjr, sjr_quartile, metric_year, works_count, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (issn_l) DO UPDATE SET name=EXCLUDED.name, "
            "openalex_source_id=EXCLUDED.openalex_source_id, sjr=EXCLUDED.sjr, "
            "sjr_quartile=EXCLUDED.sjr_quartile, metric_year=EXCLUDED.metric_year, "
            "works_count=EXCLUDED.works_count, updated_at=EXCLUDED.updated_at",
            (
                journal.get("issn_l"), journal.get("name"),
                journal.get("openalex_source_id"), journal.get("sjr"),
                journal.get("sjr_quartile"), journal.get("metric_year"),
                journal.get("works_count"), now_iso(),
            ),
        )
        pg.commit()
    finally:
        pg.close()


def journal_metrics(conn, issns: List[str]) -> Dict[str, Dict]:
    if not issns:
        return {}
    marks = ",".join("%s" for _ in issns)
    pg = pg_connection()
    try:
        rows = pg.execute(
            f"SELECT * FROM journal_catalog WHERE issn_l IN ({marks})", issns
        ).fetchall()
        return {row["issn_l"]: dict(row) for row in rows}
    finally:
        pg.close()


def dedup_key(doi: Optional[str], title: Optional[str]) -> str:
    if doi:
        return f"doi:{doi.strip().lower().replace('https://doi.org/', '')}"
    normalized = "".join(ch for ch in (title or "").lower() if ch.isalnum())
    return f"title:{hashlib.sha1(normalized.encode()).hexdigest()}"


def seen(conn, profile_id: int, key: str) -> bool:
    pg = pg_connection()
    try:
        return pg.execute(
            "SELECT 1 FROM watch_seen WHERE profile_id = %s AND dedup_key = %s",
            (profile_id, key),
        ).fetchone() is not None
    finally:
        pg.close()


def mark_seen(conn, profile_id: int, key: str, paper_id: Optional[str]) -> None:
    pg_writes.mark_seen(
        {
            "profile_id": profile_id,
            "dedup_key": key,
            "paper_id": paper_id,
            "first_seen_at": now_iso(),
        }
    )


def paper_exists(conn, doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    pg = pg_connection()
    try:
        row = pg.execute(
            "SELECT paper_id FROM papers WHERE lower(doi) = lower(%s) LIMIT 1", (doi,)
        ).fetchone()
        return row["paper_id"] if row else None
    finally:
        pg.close()


def create_run(conn, profile_id: int, start: str, end: str, owner: str = "default") -> int:
    return pg_writes.create_run(
        {
            "owner": owner,
            "profile_id": profile_id,
            "window_start": start,
            "window_end": end,
            "started_at": now_iso(),
        }
    )


def finish_run(conn, run_id: int, **stats) -> None:
    fields = [
        "status", "found", "selected", "imported_full", "imported_abstract",
        "skipped", "digest_md", "heartbeat", "error",
    ]
    updates = {k: stats[k] for k in fields if k in stats}
    updates["finished_at"] = now_iso()
    pg_writes.update_run(run_id, updates)


def get_run(conn, run_id: int) -> Optional[Dict]:
    return pg_read.get_run(run_id)


def list_runs(conn, profile_id: int, limit: int = 20) -> List[Dict]:
    return pg_read.list_runs(profile_id, limit)


def add_item(conn, run_id: int, profile_id: int, item: Dict) -> int:
    return pg_writes.create_item(
        {
            "owner": item.get("owner") or "default",
            "run_id": run_id,
            "profile_id": profile_id,
            "paper_id": item.get("paper_id"),
            "doi": item.get("doi"),
            "title": item.get("title"),
            "journal": item.get("journal"),
            "abstract": item.get("abstract"),
            "published": item.get("published"),
            "score": item.get("score"),
            "reason": item.get("reason"),
            "acquisition": item.get("acquisition"),
        }
    )


def list_items(conn, run_id: int) -> List[Dict]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM watch_items WHERE run_id = %s ORDER BY score DESC", (run_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def mark_item_read(conn, item_id: int) -> None:
    pg_writes.update_item(item_id, {"status": "read", "read_at": now_iso()})


def set_item_feedback(conn, item_id: int, feedback: str) -> None:
    pg_writes.update_item(
        item_id, {"feedback": feedback, "feedback_at": now_iso()}
    )

def delete_journal(conn, profile_id: int, issn_l: str) -> None:
    pg_writes.delete_journal(profile_id, issn_l)
