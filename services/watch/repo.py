"""Small repository layer for Watch (SQLite, no ORM)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.watch import pg_writes

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    import os

    if os.environ.get("SCIPAL_WATCH_ALLOW_SQLITE_REPO", "").strip().lower() not in {
        "1", "true", "yes", "on"
    }:
        raise RuntimeError("watch SQLite repo disabled; use pg_store")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _row(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


# ---------------------------------------------------------------- profiles
def list_profiles(conn: sqlite3.Connection, owner: Optional[str] = None) -> List[Dict]:
    if owner:
        rows = conn.execute(
            "SELECT * FROM watch_profiles WHERE owner = ? ORDER BY id", (owner,)
        )
    else:
        rows = conn.execute("SELECT * FROM watch_profiles ORDER BY id")
    return [dict(r) for r in rows]


def get_profile(
    conn: sqlite3.Connection, profile_id: int, owner: Optional[str] = None
) -> Optional[Dict]:
    row = conn.execute(
        "SELECT * FROM watch_profiles WHERE id = ?", (profile_id,)
    ).fetchone()
    if row and owner and (row["owner"] or "default") != owner:
        return None
    return _row(row)


def create_profile(conn: sqlite3.Connection, data: Dict[str, Any]) -> int:
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
    values[0] = data.get("owner") or "default"
    created_at = now_iso()
    pg_id = None
    if pg_writes.enabled():
        pg_data = {field: values[index] for index, field in enumerate(fields)}
        pg_data["created_at"] = created_at
        pg_id = pg_writes.create_profile(pg_data)
    if pg_id is not None:
        cur = conn.execute(
            f"INSERT INTO watch_profiles (id, {', '.join(fields)}, created_at) "
            f"VALUES (?, {', '.join('?' * len(fields))}, ?)",
            [pg_id, *values, created_at],
        )
    else:
        cur = conn.execute(
            f"INSERT INTO watch_profiles ({', '.join(fields)}, created_at) "
            f"VALUES ({', '.join('?' * len(fields))}, ?)",
            values + [created_at],
        )
    conn.commit()
    return int(cur.lastrowid or pg_id)


def update_profile(conn: sqlite3.Connection, profile_id: int, data: Dict[str, Any]) -> None:
    allowed = {
        "name", "field_text", "keywords", "openalex_topic_ids", "interval_days",
        "window_days", "top_journal_count", "max_items", "same_journal_limit",
        "metric_type", "metric_min", "language", "delivery", "enabled",
        "last_run_at", "next_run_at", "last_push_at", "last_heartbeat_at",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if "openalex_topic_ids" in updates and isinstance(updates["openalex_topic_ids"], (list, tuple)):
        updates["openalex_topic_ids"] = json.dumps(list(updates["openalex_topic_ids"]))
    if not updates:
        return
    if pg_writes.enabled():
        pg_writes.update_profile(profile_id, updates)
    conn.execute(
        f"UPDATE watch_profiles SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
        list(updates.values()) + [profile_id],
    )
    conn.commit()


def delete_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    if pg_writes.enabled():
        pg_writes.delete_profile(profile_id)
    conn.execute("DELETE FROM watch_profile_journals WHERE profile_id = ?", (profile_id,))
    conn.execute("DELETE FROM watch_profiles WHERE id = ?", (profile_id,))
    conn.commit()


# ---------------------------------------------------------------- journals
def list_journals(conn: sqlite3.Connection, profile_id: int) -> List[Dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM watch_profile_journals WHERE profile_id = ? ORDER BY issn_l",
            (profile_id,),
        )
    ]


def set_journals(conn: sqlite3.Connection, profile_id: int, entries: List[Dict]) -> None:
    added_at = now_iso()
    if pg_writes.enabled():
        pg_writes.replace_journals(profile_id, entries, added_at)
    conn.execute("DELETE FROM watch_profile_journals WHERE profile_id = ?", (profile_id,))
    for entry in entries:
        conn.execute(
            "INSERT OR REPLACE INTO watch_profile_journals "
            "(profile_id, issn_l, name, source, added_at) VALUES (?, ?, ?, ?, ?)",
            (
                profile_id,
                entry.get("issn_l"),
                entry.get("name"),
                entry.get("source", "auto"),
                added_at,
            ),
        )
    conn.commit()


def upsert_journal(conn: sqlite3.Connection, journal: Dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO journal_catalog "
        "(issn_l, name, openalex_source_id, sjr, sjr_quartile, metric_year, works_count, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            journal.get("issn_l"),
            journal.get("name"),
            journal.get("openalex_source_id"),
            journal.get("sjr"),
            journal.get("sjr_quartile"),
            journal.get("metric_year"),
            journal.get("works_count"),
            now_iso(),
        ),
    )


def journal_metrics(conn: sqlite3.Connection, issns: List[str]) -> Dict[str, Dict]:
    if not issns:
        return {}
    marks = ",".join("?" * len(issns))
    rows = conn.execute(
        f"SELECT * FROM journal_catalog WHERE issn_l IN ({marks})", issns
    ).fetchall()
    return {r["issn_l"]: dict(r) for r in rows}


# ---------------------------------------------------------------- runs/items
def create_run(
    conn: sqlite3.Connection,
    profile_id: int,
    start: str,
    end: str,
    owner: str = "default",
) -> int:
    started_at = now_iso()
    pg_id = None
    if pg_writes.enabled():
        pg_id = pg_writes.create_run(
            {
                "owner": owner,
                "profile_id": profile_id,
                "window_start": start,
                "window_end": end,
                "started_at": started_at,
            }
        )
    if pg_id is not None:
        cur = conn.execute(
            "INSERT INTO watch_runs (id, owner, profile_id, window_start, window_end, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, 'running', ?)",
            (pg_id, owner, profile_id, start, end, started_at),
        )
    else:
        cur = conn.execute(
            "INSERT INTO watch_runs (owner, profile_id, window_start, window_end, status, started_at) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            (owner, profile_id, start, end, started_at),
        )
    conn.commit()
    return int(cur.lastrowid or pg_id)


def finish_run(conn: sqlite3.Connection, run_id: int, **stats) -> None:
    fields = ["status", "found", "selected", "imported_full", "imported_abstract",
              "skipped", "digest_md", "heartbeat", "error"]
    updates = {k: stats[k] for k in fields if k in stats}
    updates["finished_at"] = now_iso()
    if pg_writes.enabled():
        pg_writes.update_run(run_id, updates)
    conn.execute(
        f"UPDATE watch_runs SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
        list(updates.values()) + [run_id],
    )
    conn.commit()


def add_item(conn: sqlite3.Connection, run_id: int, profile_id: int, item: Dict) -> int:
    row = {
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
    pg_id = pg_writes.create_item(row) if pg_writes.enabled() else None
    if pg_id is not None:
        cur = conn.execute(
            "INSERT INTO watch_items (id, owner, run_id, profile_id, paper_id, doi, title, journal, "
            "abstract, published, score, reason, acquisition, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')",
            (pg_id, *row.values()),
        )
    else:
        cur = conn.execute(
            "INSERT INTO watch_items (owner, run_id, profile_id, paper_id, doi, title, journal, "
            "abstract, published, score, reason, acquisition, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')",
            tuple(row.values()),
        )
    conn.commit()
    return int(cur.lastrowid or pg_id)


def list_runs(conn: sqlite3.Connection, profile_id: int, limit: int = 20) -> List[Dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM watch_runs WHERE profile_id = ? ORDER BY id DESC LIMIT ?",
            (profile_id, limit),
        )
    ]


def get_run(conn: sqlite3.Connection, run_id: int) -> Optional[Dict]:
    return _row(conn.execute("SELECT * FROM watch_runs WHERE id = ?", (run_id,)).fetchone())


def list_items(conn: sqlite3.Connection, run_id: int) -> List[Dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM watch_items WHERE run_id = ? ORDER BY score DESC", (run_id,)
        )
    ]


def mark_item_read(conn: sqlite3.Connection, item_id: int) -> None:
    now = now_iso()
    if pg_writes.enabled():
        pg_writes.update_item(item_id, {"status": "read", "read_at": now})
    conn.execute(
        "UPDATE watch_items SET status = 'read', read_at = ? WHERE id = ?",
        (now, item_id),
    )
    conn.commit()


def set_item_feedback(conn: sqlite3.Connection, item_id: int, feedback: str) -> None:
    now = now_iso()
    if pg_writes.enabled():
        pg_writes.update_item(item_id, {"feedback": feedback, "feedback_at": now})
    conn.execute(
        "UPDATE watch_items SET feedback = ?, feedback_at = ? WHERE id = ?",
        (feedback, now, item_id),
    )
    conn.commit()


# ---------------------------------------------------------------- dedup
def dedup_key(doi: Optional[str], title: Optional[str]) -> str:
    if doi:
        return f"doi:{doi.strip().lower().replace('https://doi.org/', '')}"
    normalized = "".join(ch for ch in (title or "").lower() if ch.isalnum())
    return f"title:{hashlib.sha1(normalized.encode()).hexdigest()}"


def seen(conn: sqlite3.Connection, profile_id: int, key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM watch_seen WHERE profile_id = ? AND dedup_key = ?",
        (profile_id, key),
    ).fetchone() is not None


def mark_seen(conn: sqlite3.Connection, profile_id: int, key: str, paper_id: Optional[str]) -> None:
    now = now_iso()
    if pg_writes.enabled():
        pg_writes.mark_seen(
            {"profile_id": profile_id, "dedup_key": key, "paper_id": paper_id, "first_seen_at": now}
        )
    conn.execute(
        "INSERT OR IGNORE INTO watch_seen (profile_id, dedup_key, paper_id, first_seen_at, status) "
        "VALUES (?, ?, ?, ?, 'new')",
        (profile_id, key, paper_id, now),
    )


def paper_exists(conn: sqlite3.Connection, doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    row = conn.execute(
        "SELECT paper_id FROM papers WHERE lower(doi) = lower(?) LIMIT 1", (doi,)
    ).fetchone()
    return row[0] if row else None
