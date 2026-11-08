"""Auto-merging: expand multi-hit sections into parent context (PostgreSQL)."""

from __future__ import annotations

from typing import Dict, List

from services.db.pg_pool import main_read_connection


def _estimate(text: str) -> int:
    return max(1, int(len((text or "").split()) * 1.3))


class AutoMerger:
    def __init__(self, db_path=None) -> None:
        # Kept for call-site compatibility; the store is PostgreSQL now.
        self.db_path = db_path

    def merge(
        self,
        contexts: List[Dict],
        min_hits: int = 2,
        token_budget: int = 1200,
    ) -> List[Dict]:
        if not contexts:
            return contexts
        pg = main_read_connection()
        used = 0
        try:
            for context in contexts:
                matched = context.get("matched_para_ids") or []
                if len(matched) < min_hits:
                    continue
                section_id = context.get("section_id")
                if not section_id:
                    continue
                rows = pg.execute(
                    "SELECT para_id, text, page, sequence FROM paragraphs "
                    "WHERE section_id = %s ORDER BY sequence",
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
            pg.close()
