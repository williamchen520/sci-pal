"""PostgreSQL systematic-review projects (G3.10e4a)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.db.pg_pool import pg_connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project(
    name: str,
    field_text: str = "",
    pico: Optional[Dict[str, str]] = None,
    owner: str = "default",
) -> str:
    project_id = "rev_" + uuid.uuid4().hex[:10]
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO review_projects (project_id, owner, name, field_text, pico_json, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (project_id, owner, name, field_text, json.dumps(pico or {}, ensure_ascii=False), _now()),
        )
        pg.commit()
    finally:
        pg.close()
    return project_id


def get_project(project_id: str) -> Optional[Dict]:
    pg = pg_connection()
    try:
        row = pg.execute(
            "SELECT project_id, owner, name, field_text, pico_json "
            "FROM review_projects WHERE project_id = %s",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "project_id": row["project_id"],
            "owner": row["owner"],
            "name": row["name"],
            "field_text": row["field_text"],
            "pico": json.loads(row["pico_json"] or "{}"),
        }
    finally:
        pg.close()


def list_projects(owner: str = "default") -> List[Dict]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT DISTINCT p.project_id, p.name, p.field_text, p.pico_json, p.created_at "
            "FROM review_projects p LEFT JOIN review_project_members m "
            "ON m.project_id = p.project_id WHERE p.owner = %s OR m.member = %s "
            "ORDER BY p.created_at DESC",
            (owner, owner),
        ).fetchall()
        return [
            {
                "project_id": row["project_id"],
                "name": row["name"],
                "field_text": row["field_text"],
                "pico": json.loads(row["pico_json"] or "{}"),
            }
            for row in rows
        ]
    finally:
        pg.close()


def can_access(project_id: str, user: str) -> bool:
    pg = pg_connection()
    try:
        if pg.execute(
            "SELECT 1 FROM review_projects WHERE project_id = %s AND owner = %s",
            (project_id, user),
        ).fetchone():
            return True
        return bool(
            pg.execute(
                "SELECT 1 FROM review_project_members WHERE project_id = %s AND member = %s",
                (project_id, user),
            ).fetchone()
        )
    finally:
        pg.close()


def add_member(project_id: str, member: str, role: str = "reviewer") -> None:
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO review_project_members (project_id, member, role, added_at) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (project_id, member) DO UPDATE SET role=EXCLUDED.role",
            (project_id, member, role, _now()),
        )
        pg.commit()
    finally:
        pg.close()


def members(project_id: str) -> List[Dict]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT member, role FROM review_project_members WHERE project_id = %s ORDER BY member",
            (project_id,),
        ).fetchall()
        return [{"member": row["member"], "role": row["role"]} for row in rows]
    finally:
        pg.close()


def add_papers(project_id: str, paper_ids: List[str]) -> int:
    pg = pg_connection()
    try:
        for paper_id in paper_ids:
            pg.execute(
                "INSERT INTO review_project_papers (project_id, paper_id, added_at) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (project_id, paper_id, _now()),
            )
        pg.commit()
        return len(paper_ids)
    finally:
        pg.close()

def screen(
    project_id: str,
    paper_id: str,
    decision: str,
    reason: str = "",
    reviewer: str = "",
    stage: str = "title_abstract",
) -> None:
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO screening_decisions "
            "(project_id, paper_id, stage, decision, reason, reviewer, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (project_id, paper_id, stage, decision, reason, reviewer, _now()),
        )
        pg.commit()
    finally:
        pg.close()


def adjudicate(
    project_id: str,
    paper_id: str,
    decision: str,
    reason: str = "",
    editor: str = "",
) -> None:
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO adjudications "
            "(project_id, paper_id, decision, reason, editor, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (project_id, paper_id, decision, reason, editor, _now()),
        )
        pg.commit()
    finally:
        pg.close()


def _latest_adjudications(project_id: str) -> Dict[str, str]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT paper_id, decision FROM ("
            " SELECT paper_id, decision, ROW_NUMBER() OVER ("
            " PARTITION BY paper_id ORDER BY id DESC) AS rn"
            " FROM adjudications WHERE project_id = %s"
            ") t WHERE rn = 1",
            (project_id,),
        ).fetchall()
        return {row["paper_id"]: row["decision"] for row in rows}
    finally:
        pg.close()


def prisma(project_id: str) -> Dict[str, int]:
    pg = pg_connection()
    try:
        identified = pg.execute(
            "SELECT COUNT(*) AS n FROM review_project_papers WHERE project_id = %s",
            (project_id,),
        ).fetchone()["n"]
        rows = pg.execute(
            "SELECT paper_id, decision FROM ("
            " SELECT paper_id, decision, ROW_NUMBER() OVER ("
            " PARTITION BY paper_id ORDER BY id DESC) AS rn"
            " FROM screening_decisions WHERE project_id = %s"
            ") t WHERE rn = 1",
            (project_id,),
        ).fetchall()
        decisions = {row["paper_id"]: row["decision"] for row in rows}
    finally:
        pg.close()
    decisions.update(_latest_adjudications(project_id))
    counts: Dict[str, int] = {}
    for decision in decisions.values():
        counts[decision] = counts.get(decision, 0) + 1
    included = counts.get("include", 0)
    excluded = counts.get("exclude", 0)
    return {
        "identified": identified,
        "screened": sum(counts.values()),
        "included": included,
        "excluded": excluded,
        "pending": max(identified - included - excluded, 0),
    }


def conflicts(project_id: str, stage: str = "title_abstract") -> List[Dict]:
    pg = pg_connection()
    try:
        rows = pg.execute(
            "SELECT paper_id, reviewer, decision FROM ("
            " SELECT paper_id, reviewer, decision, ROW_NUMBER() OVER ("
            " PARTITION BY paper_id, reviewer ORDER BY id DESC) AS rn"
            " FROM screening_decisions WHERE project_id = %s AND stage = %s"
            " AND reviewer <> '') t WHERE rn = 1 ORDER BY paper_id",
            (project_id, stage),
        ).fetchall()
    finally:
        pg.close()
    by_paper: Dict[str, Dict[str, str]] = {}
    for row in rows:
        by_paper.setdefault(row["paper_id"], {})[row["reviewer"]] = row["decision"]
    resolved = _latest_adjudications(project_id)
    return [
        {
            "paper_id": paper_id,
            "decisions": decisions,
            "resolved": paper_id in resolved,
            "adjudicated": resolved.get(paper_id),
        }
        for paper_id, decisions in by_paper.items()
        if len(set(decisions.values())) > 1
    ]


def log_event(project_id: str, actor: str, action: str, target: str = "", detail: str = "") -> None:
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO review_events (project_id, actor, action, target, detail, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (project_id, actor, action, target, detail, _now()),
        )
        pg.commit()
    finally:
        pg.close()
