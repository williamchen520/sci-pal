"""Workspace-aware filtering for retrieval results."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from config.settings import DATABASE_PATH


def allowed_paper_ids(
    workspace_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> set[str]:
    from services.db.pg_pool import core_connection

    pg = main_read_connection()
    try:
        rows = pg.execute(
            "SELECT paper_id FROM papers WHERE workspace_id = %s", (workspace_id,)
        ).fetchall()
        return {row["paper_id"] for row in rows}
    finally:
        pg.close()


def item_paper_id(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    paper_id = item.get("paper_id")
    if paper_id:
        return str(paper_id)
    paper = item.get("paper")
    if isinstance(paper, dict) and paper.get("paper_id"):
        return str(paper["paper_id"])
    metadata = item.get("metadata")
    if isinstance(metadata, dict) and metadata.get("paper_id"):
        return str(metadata["paper_id"])
    return None


def filter_items(items: Iterable[Any], allowed: set[str]) -> list[Any]:
    return [item for item in items if item_paper_id(item) in allowed]


def filter_retrieval_result(result: dict, allowed: set[str]) -> dict:
    """Drop local hits outside the workspace before they reach the LLM."""
    for key in (
        "paragraphs",
        "parent_contexts",
        "summaries",
        "chunks",
        "figures",
        "tables",
        "papers",
        "graph_neighbors",
        "abstracts",
    ):
        if isinstance(result.get(key), list):
            result[key] = filter_items(result[key], allowed)
    return result
