"""Personal notes service (PostgreSQL only)."""

from __future__ import annotations

from services.notes import pg_service


def list_notes(
    workspace_id: str,
    user_id: str,
    *,
    paper_id: str | None = None,
    db_path=None,
) -> list[dict]:
    return pg_service.list_notes(workspace_id, user_id, paper_id=paper_id)


def paper_in_workspace(paper_id: str, workspace_id: str) -> bool:
    return pg_service.paper_in_workspace(paper_id, workspace_id)


def create_note(
    workspace_id: str,
    user_id: str,
    content: str,
    *,
    paper_id: str | None = None,
    para_id: str | None = None,
    db_path=None,
) -> dict:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")
    return pg_service.create_note(
        workspace_id, user_id, content, paper_id=paper_id, para_id=para_id
    )


def update_note(
    note_id: str,
    workspace_id: str,
    user_id: str,
    content: str,
    *,
    db_path=None,
) -> dict | None:
    content = (content or "").strip()
    if not content:
        raise ValueError("content is required")
    return pg_service.update_note(note_id, workspace_id, user_id, content)


def delete_note(
    note_id: str,
    workspace_id: str,
    user_id: str,
    *,
    db_path=None,
) -> bool:
    return pg_service.delete_note(note_id, workspace_id, user_id)
