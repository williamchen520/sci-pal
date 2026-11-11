"""PostgreSQL read adapter for protocols (G3.10e2a)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.db.pg_pool import core_connection


def list_protocols(limit: int = 50, offset: int = 0, query: str = "") -> List[Dict[str, Any]]:
    where = ""
    params: list = []
    text = str(query or "").strip()
    if text:
        where = "WHERE p.title ILIKE %s OR p.doi ILIKE %s"
        params.extend([f"%{text}%", f"%{text}%"])
    params.extend([max(1, limit), max(0, offset)])
    pg = core_connection()
    try:
        rows = pg.execute(
            f"""
            SELECT p.protocol_id, p.title, p.doi, p.version, p.url, p.fetched_at,
                   (SELECT COUNT(*) FROM protocol_steps s WHERE s.protocol_id = p.protocol_id) AS steps
            FROM protocol_imports p {where}
            ORDER BY p.fetched_at DESC LIMIT %s OFFSET %s
            """,
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def count_protocols(query: str = "") -> int:
    text = str(query or "").strip()
    pg = core_connection()
    try:
        if text:
            row = pg.execute(
                "SELECT COUNT(*) AS n FROM protocol_imports WHERE title ILIKE %s OR doi ILIKE %s",
                (f"%{text}%", f"%{text}%"),
            ).fetchone()
        else:
            row = pg.execute("SELECT COUNT(*) AS n FROM protocol_imports").fetchone()
        return int(row["n"])
    finally:
        pg.close()


def get_protocol(protocol_id: str) -> Optional[Dict[str, Any]]:
    pg = core_connection()
    try:
        row = pg.execute(
            "SELECT * FROM protocol_imports WHERE protocol_id = %s", (protocol_id,)
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["steps"] = [
            {
                **dict(step),
                "reagents": json.loads(step.get("reagents_json") or "[]"),
            }
            for step in pg.execute(
                "SELECT * FROM protocol_steps WHERE protocol_id = %s ORDER BY ordinal",
                (protocol_id,),
            ).fetchall()
        ]
        record.pop("raw_json", None)
        return record
    finally:
        pg.close()
