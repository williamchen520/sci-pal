"""Auto-merging: expand multi-hit sections into parent context."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"


def _estimate(text: str) -> int:
    return max(1, int(len((text or "").split()) * 1.3))


class AutoMerger:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = str(db_path)

    def merge(
        self,
        contexts: List[Dict],
        min_hits: int = 2,
        token_budget: int = 1200,
    ) -> List[Dict]:
        if not contexts:
            return contexts
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        used = 0
        try:
            for context in contexts:
                matched = context.get("matched_para_ids") or []
                if len(matched) < min_hits:
                    continue
                section_id = context.get("section_id")
                if not section_id:
                    continue
                rows = conn.execute(
                    "SELECT para_id, text, page, sequence FROM paragraphs "
                    "WHERE section_id = ? ORDER BY sequence",
                    (section_id,),
                ).fetchall()
                existing = {
                    item.get("para_id") for item in context.get("paragraphs") or []
                }
                text_parts = [context.get("text") or ""]
                for row in rows:
                    if row["para_id"] in existing:
                        continue
                    tokens = _estimate(row["text"])
                    if used + tokens > token_budget:
                        break
                    used += tokens
                    context.setdefault("paragraphs", []).append(
                        {
                            "para_id": row["para_id"],
                            "text": row["text"],
                            "page": row["page"],
                            "sequence": row["sequence"],
                        }
                    )
                    text_parts.append(row["text"])
                context["text"] = "\n\n".join(part for part in text_parts if part)
                context["auto_merged"] = True
            return contexts
        finally:
            conn.close()
