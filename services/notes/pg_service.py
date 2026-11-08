"""PostgreSQL-only personal notes backend."""

from __future__ import annotations

import uuid
from typing import Optional

from services.db.pg_pool import pg_connection
from services.db.tenant_pilot import set_search_path


def _row(row) -> dict:
    return dict(row)


def _pg():
    pg = pg_connection()
    set_search_path(pg, "notes")
    return pg


def list_notes(
    workspace_id: str,
    user_id: str,
    *,
    paper_id: Optional[str] = None,
) -> list[dict]:
    pg = _pg()
    try:
        sql = (
            "SELECT note_id, paper_id, para_id, content, created_at, updated_at "
            "FROM notes WHERE workspace_id = %s AND user_id = %s"
        )
        params: list = [workspace_id, user_id]
        if paper_id:
            sql += " AND paper_id = %s"
            params.append(paper_id)
        sql += " ORDER BY updated_at DESC, note_id"
        return [_row(row) for row in pg.execute(sql, params).fetchall()]
    finally:
        pg.close()


def paper_in_workspace(paper_id: str, workspace_id: str) -> bool:
    pg = _pg()
    try:
        row = pg.execute(
            "SELECT 1 FROM papers WHERE paper_id = %s AND workspace_id = %s",
            (paper_id, workspace_id),
        ).fetchone()
        return bool(row)
    finally:
        pg.close()


def create_note(
    workspace_id: str,
    user_id: str,
    content: str,
    *,
    paper_id: Optional[str] = None,
    para_id: Optional[str] = None,
) -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")
    if paper_id and not paper_in_workspace(paper_id, workspace_id):
        raise PermissionError("paper not found in workspace")
    note_id = f"note_{uuid.uuid4().hex}"
    pg = _pg()
    try:
        pg.execute(
            "INSERT INTO notes (note_id, user_id, workspace_id, paper_id, para_id, content) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (note_id, user_id, workspace_id, paper_id, para_id, content),
        )
        pg.commit()
        row = pg.execute(
            "SELECT note_id, paper_id, para_id, content, created_at, updated_at "
            "FROM notes WHERE note_id = %s",
            (note_id,),
        ).fetchone()
        return _row(row)
    finally:
        pg.close()


def update_note(
    note_id: str,
    workspace_id: str,
    user_id: str,
    content: str,
) -> Optional[dict]:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")
    pg = _pg()
    try:
        row = pg.execute(
            "UPDATE notes SET content = %s, updated_at = now() "
            "WHERE note_id = %s AND workspace_id = %s AND user_id = %s "
            "RETURNING note_id, paper_id, para_id, content, created_at, updated_at",
            (content, note_id, workspace_id, user_id),
        ).fetchone()
        pg.commit()
        return _row(row) if row else None
    finally:
        pg.close()


def delete_note(note_id: str, workspace_id: str, user_id: str) -> bool:
    pg = _pg()
    try:
        row = pg.execute(
            "DELETE FROM notes WHERE note_id = %s AND workspace_id = %s AND user_id = %s "
            "RETURNING note_id",
            (note_id, workspace_id, user_id),
        ).fetchone()
        pg.commit()
        return bool(row)
    finally:
        pg.close()
