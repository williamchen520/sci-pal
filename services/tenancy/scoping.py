"""Workspace-aware filtering for retrieval results."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from config.settings import DATABASE_PATH


def allowed_paper_ids(
    workspace_id: str,
    *,
    db_path: str | Path = DATABASE_PATH,
) -> set[str]:
    path = Path(db_path)
    if not path.exists():
        return set()
    conn = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "papers" not in tables:
            return set()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(papers)")}
        if "workspace_id" not in columns:
            conn.execute("ALTER TABLE papers ADD COLUMN workspace_id TEXT DEFAULT 'ws_default'")
            conn.commit()
        return {
            row[0]
            for row in conn.execute(
                "SELECT paper_id FROM papers WHERE workspace_id = ?", (workspace_id,)
            )
        }
    finally:
        conn.close()


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
