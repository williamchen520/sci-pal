"""Beam best-first section routing over the section tree."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from services.search.section_types import classify_section, query_intent, section_prior

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


class TreeRouter:
    def __init__(
        self,
        db_path: Path | str = DB_PATH,
        summary_search: Optional[Callable[..., List[Dict]]] = None,
    ):
        self.db_path = str(db_path)
        self.summary_search = summary_search

    def _summary_scores(self, query: str, paper_id: str) -> Dict[str, float]:
        if self.summary_search is None:
            return {}
        try:
            hits = self.summary_search(query, top_k=50, paper_id=paper_id)
        except Exception:  # noqa: BLE001
            return {}
        return {
            hit.get("section_id"): max(0.0, 1.0 - float(hit.get("distance") or 1.0))
            for hit in hits
            if hit.get("section_id")
        }

    def search(
        self,
        query: str,
        paper_ids: Iterable[str],
        beam: int = 4,
        depth: int = 3,
        max_sections: int = 8,
        paragraph_scores: Optional[Dict[str, float]] = None,
    ) -> List[Dict]:
        paper_ids = list(dict.fromkeys(pid for pid in paper_ids if pid))
        if not paper_ids:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        intent = query_intent(query)
        paragraph_scores = paragraph_scores or {}
        max_para = max(paragraph_scores.values(), default=1.0) or 1.0
        collected: Dict[str, Dict] = {}
        try:
            for paper_id in paper_ids[:5]:
                scores = self._summary_scores(query, paper_id)
                roots = conn.execute(
                    "SELECT section_id, paper_id, title, depth, path FROM sections "
                    "WHERE paper_id = ? AND (depth = 1 OR parent_id IS NULL OR parent_id = '')",
                    (paper_id,),
                ).fetchall()
                if not roots:
                    roots = conn.execute(
                        "SELECT section_id, paper_id, title, depth, path FROM sections "
                        "WHERE paper_id = ? AND depth = 1",
                        (paper_id,),
                    ).fetchall()
                frontier = []
                for row in roots:
                    title = row["title"] or ""
                    para_score = paragraph_scores.get(row["section_id"], 0.0) / max_para
                    prior = section_prior(intent, classify_section(title))
                    score = (
                        0.5 * para_score
                        + 0.3 * scores.get(row["section_id"], 0.0)
                        + 0.2 * (prior / 0.15 if prior > 0 else 0.0)
                    )
                    frontier.append(
                        {
                            "section_id": row["section_id"],
                            "paper_id": row["paper_id"],
                            "title": title,
                            "depth": row["depth"] or 1,
                            "score": score,
                        }
                    )
                frontier = sorted(frontier, key=lambda item: -item["score"])[:beam]
                for level in range(depth):
                    for node in frontier:
                        collected[node["section_id"]] = node
                    if not frontier:
                        break
                    marks = ",".join("?" * len(frontier))
                    children = conn.execute(
                        "SELECT section_id, paper_id, parent_id, title, depth, path FROM sections "
                        f"WHERE parent_id IN ({marks})",
                        [node["section_id"] for node in frontier],
                    ).fetchall()
                    next_frontier = []
                    frontier_scores = {node["section_id"]: node["score"] for node in frontier}
                    for row in children:
                        title = row["title"] or ""
                        parent_score = frontier_scores.get(row["parent_id"], 0.0)
                        para_score = (
                            paragraph_scores.get(row["section_id"], 0.0) / max_para
                        )
                        prior = section_prior(intent, classify_section(title))
                        score = (
                            0.5 * parent_score
                            + 0.2 * para_score
                            + 0.2 * scores.get(row["section_id"], 0.0)
                            + 0.1 * (prior / 0.15 if prior > 0 else 0.0)
                        )
                        next_frontier.append(
                            {
                                "section_id": row["section_id"],
                                "paper_id": row["paper_id"],
                                "title": title,
                                "depth": row["depth"] or (level + 2),
                                "score": score,
                            }
                        )
                    frontier = sorted(next_frontier, key=lambda item: -item["score"])[:beam]
            ranked = sorted(collected.values(), key=lambda item: -item["score"])
            return ranked[:max_sections]
        finally:
            conn.close()
