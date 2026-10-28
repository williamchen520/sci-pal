"""Minimal RetrievalNode contract shared by summaries, paragraphs and sentences."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class RetrievalNode:
    node_id: str
    level: str  # sentence | paragraph | section | paper
    text: str
    paper_id: str = ""
    section_id: str = ""
    parent_id: str = ""
    source_sentence_ids: List[str] = field(default_factory=list)
    score: float = 0.0
    metadata: Dict = field(default_factory=dict)

    def as_candidate(self) -> Dict:
        return {
            "para_id": self.node_id if self.level == "paragraph" else None,
            "paper_id": self.paper_id,
            "section_id": self.section_id,
            "text": self.text,
            "score": self.score,
            "section_l1": self.metadata.get("section_l1", ""),
            "section_l2": self.metadata.get("section_l2", ""),
            "node_level": self.level,
            "source": self.metadata.get("source", ""),
        }


def paragraph_nodes(db_path: Path | str, section_ids: List[str], limit: int = 300) -> List[RetrievalNode]:
    if not section_ids:
        return []
    marks = ",".join("?" * len(section_ids))
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT para_id, paper_id, section_id, text, section_level1, section_level2 "
            f"FROM paragraphs WHERE section_id IN ({marks}) LIMIT ?",
            (*section_ids, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        RetrievalNode(
            node_id=row["para_id"],
            level="paragraph",
            text=row["text"] or "",
            paper_id=row["paper_id"] or "",
            section_id=row["section_id"] or "",
            parent_id=row["section_id"] or "",
            metadata={
                "section_l1": row["section_level1"] or "",
                "section_l2": row["section_level2"] or "",
                "source": "summary_child",
            },
        )
        for row in rows
    ]
