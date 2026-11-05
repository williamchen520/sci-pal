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
