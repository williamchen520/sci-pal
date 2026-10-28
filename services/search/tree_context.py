"""Tree-aware context builder (sentence -> paragraph -> section)."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "research.db"
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
HIT_START = "►"
HIT_END = "◄"


@dataclass
class TreeNode:
    node_id: str
    level: str
    text: str
    parent_id: str = ""
    paper_id: str = ""
    section_id: str = ""
    sentence_ids: List[str] = field(default_factory=list)
    score: float = 0.0
    tokens: int = 0


def _tokens(text: str) -> set:
    return {token.lower() for token in TOKEN_RE.findall(text or "") if len(token) > 1}


def _estimate_tokens(text: str) -> int:
    return max(1, int(len((text or "").split()) * 1.3))


class TreeContextBuilder:
    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = str(db_path)

    def build(
        self,
        hits: List[Dict],
        query: str,
        token_budget: int = 1200,
        max_sections: int = 4,
        max_paragraphs: int = 4,
        max_sentences: int = 2,
    ) -> List[Dict]:
        if not hits:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query_tokens = _tokens(query)
        try:
            sections: Dict[str, Dict] = {}
            for hit in hits:
                para_id = hit.get("para_id")
                if not para_id:
                    continue
                row = conn.execute(
                    "SELECT p.para_id, p.paper_id, p.section_id, p.text, p.sequence, p.page, "
                    "s.path, s.title FROM paragraphs p "
                    "LEFT JOIN sections s ON s.section_id = p.section_id "
                    "WHERE p.para_id = ?",
                    (para_id,),
                ).fetchone()
                if not row:
                    continue
                group = sections.setdefault(
                    row["section_id"] or f"solo::{row['paper_id']}::{row['para_id']}",
                    {
                        "paper_id": row["paper_id"],
                        "section_id": row["section_id"] or "",
                        "title": row["title"] or "",
                        "path": row["path"] or "",
                        "hits": [],
                        "score": 0.0,
                    },
                )
                group["hits"].append((hit.get("rerank_score") or hit.get("score") or 0.0, row))
                group["score"] = max(group["score"], group["hits"][-1][0])

            ordered_sections = sorted(sections.values(), key=lambda item: -item["score"])
            contexts: List[Dict] = []
            used_tokens = 0
            for section in ordered_sections[:max_sections]:
                if used_tokens >= token_budget:
                    break
                paragraphs = conn.execute(
                    "SELECT para_id, text, sequence, page FROM paragraphs "
                    "WHERE section_id = ? ORDER BY sequence",
                    (section["section_id"],),
                ).fetchall() if section["section_id"] else []
                if not paragraphs:
                    paragraphs = [hit[1] for hit in section["hits"][:1]]
                hit_ids = {hit[1]["para_id"] for hit in section["hits"]}
                hit_sequences = [hit[1]["sequence"] for hit in section["hits"] if hit[1]["sequence"]]
                anchor = min(hit_sequences) if hit_sequences else 0
                ordered = sorted(
                    paragraphs,
                    key=lambda row: (
                        row["para_id"] not in hit_ids,
                        abs((row["sequence"] or 0) - anchor),
                    ),
                )[:max_paragraphs]

                selected = []
                matched_sentences = []
                text_parts = []
                for paragraph in ordered:
                    sentences = conn.execute(
                        "SELECT sentence_id, text, page FROM sentences "
                        "WHERE para_id = ? ORDER BY sequence",
                        (paragraph["para_id"],),
                    ).fetchall()
                    if not sentences:
                        continue
                    ranked = sorted(
                        sentences,
                        key=lambda sentence: len(query_tokens & _tokens(sentence["text"])),
                        reverse=True,
                    )[:max_sentences]
                    if ranked:
                        best = ranked[0]
                        marked = paragraph["text"].replace(
                            best["text"], f"{HIT_START}{best['text']}{HIT_END}", 1
                        )
                    else:
                        best = sentences[0]
                        marked = f"{HIT_START} {paragraph['text']} {HIT_END}"
                    content = " ".join(
                        [paragraph["text"]] + [s["text"] for s in ranked]
                    )
                    tokens = _estimate_tokens(content)
                    if used_tokens + tokens > token_budget and selected:
                        break
                    selected.append(
                        {
                            "para_id": paragraph["para_id"],
                            "text": paragraph["text"],
                            "page": paragraph["page"],
                            "sequence": paragraph["sequence"],
                        }
                    )
                    matched_sentences.extend(
                        {"sentence_id": s["sentence_id"], "text": s["text"], "page": s["page"]}
                        for s in ranked
                    )
                    text_parts.append(marked)
                    used_tokens += tokens
                    if used_tokens >= token_budget:
                        break

                if not selected:
                    continue
                path = [part for part in (section["path"] or "").split("›") if part.strip()]
                contexts.append(
                    {
                        "paper_id": section["paper_id"],
                        "section_id": section["section_id"],
                        "section": section["title"],
                        "section_path": path or [section["title"]],
                        "page": selected[0].get("page"),
                        "score": section["score"],
                        "mode": "tree",
                        "matched_para_ids": [item["para_id"] for item in selected],
                        "matched_sentences": matched_sentences,
                        "paragraphs": selected,
                        "text": "\n\n".join(text_parts),
                        "tokens": used_tokens,
                    }
                )
            return contexts
        finally:
            conn.close()
