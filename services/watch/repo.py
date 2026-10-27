"""Small repository layer for Watch (SQLite, no ORM)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_DB = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _row(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


# ---------------------------------------------------------------- profiles
def list_profiles(conn: sqlite3.Connection) -> List[Dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM watch_profiles ORDER BY id")]


def get_profile(conn: sqlite3.Connection, profile_id: int) -> Optional[Dict]:
    return _row(conn.execute("SELECT * FROM watch_profiles WHERE id = ?", (profile_id,)).fetchone())


def create_profile(conn: sqlite3.Connection, data: Dict[str, Any]) -> int:
    fields = [
        "name", "field_text", "keywords", "openalex_topic_ids", "interval_days",
        "window_days", "top_journal_count", "max_items", "same_journal_limit",
        "metric_type", "metric_min", "language", "delivery", "enabled",
    ]
    values = [data.get(f) for f in fields]
    if isinstance(data.get("openalex_topic_ids"), (list, tuple)):
        values[3] = json.dumps(list(data["openalex_topic_ids"]))
    if not data.get("name"):
        raise ValueError("name required")
    cur = conn.execute(
        f"INSERT INTO watch_profiles ({', '.join(fields)}, created_at) "
        f"VALUES ({', '.join('?' * len(fields))}, ?)",
        values + [now_iso()],
    )
    conn.commit()
    return int(cur.lastrowid)


def update_profile(conn: sqlite3.Connection, profile_id: int, data: Dict[str, Any]) -> None:
    allowed = {
        "name", "field_text", "keywords", "openalex_topic_ids", "interval_days",
        "window_days", "top_journal_count", "max_items", "same_journal_limit",
        "metric_type", "metric_min", "language", "delivery", "enabled",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if "openalex_topic_ids" in updates and isinstance(updates["openalex_topic_ids"], (list, tuple)):
        updates["openalex_topic_ids"] = json.dumps(list(updates["openalex_topic_ids"]))
    if not updates:
        return
    conn.execute(
        f"UPDATE watch_profiles SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
        list(updates.values()) + [profile_id],
    )
    conn.commit()


def delete_profile(conn: sqlite3.Connection, profile_id: int) -> None:
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
                now_iso(),
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
def create_run(conn: sqlite3.Connection, profile_id: int, start: str, end: str) -> int:
    cur = conn.execute(
        "INSERT INTO watch_runs (profile_id, window_start, window_end, status, started_at) "
        "VALUES (?, ?, ?, 'running', ?)",
        (profile_id, start, end, now_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, **stats) -> None:
    fields = ["status", "found", "selected", "imported_full", "imported_abstract",
              "skipped", "digest_md", "error"]
    updates = {k: stats[k] for k in fields if k in stats}
    updates["finished_at"] = now_iso()
    conn.execute(
        f"UPDATE watch_runs SET {', '.join(f'{k} = ?' for k in updates)} WHERE id = ?",
        list(updates.values()) + [run_id],
    )
    conn.commit()


def add_item(conn: sqlite3.Connection, run_id: int, profile_id: int, item: Dict) -> int:
    cur = conn.execute(
        "INSERT INTO watch_items (run_id, profile_id, paper_id, doi, title, journal, "
        "published, score, reason, acquisition, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new')",
        (
            run_id, profile_id, item.get("paper_id"), item.get("doi"), item.get("title"),
            item.get("journal"), item.get("published"), item.get("score"),
            item.get("reason"), item.get("acquisition"),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


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
    conn.execute(
        "UPDATE watch_items SET status = 'read', read_at = ? WHERE id = ?",
        (now_iso(), item_id),
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
    conn.execute(
        "INSERT OR IGNORE INTO watch_seen (profile_id, dedup_key, paper_id, first_seen_at, status) "
        "VALUES (?, ?, ?, ?, 'new')",
        (profile_id, key, paper_id, now_iso()),
    )


def paper_exists(conn: sqlite3.Connection, doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    row = conn.execute(
        "SELECT paper_id FROM papers WHERE lower(doi) = lower(?) LIMIT 1", (doi,)
    ).fetchone()
    return row[0] if row else None
