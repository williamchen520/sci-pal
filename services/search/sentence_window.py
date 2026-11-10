"""Sentence-window context builder.

Ranking happens on anchor sentences only. Neighbour sentences are returned as
unscored context so they never influence RRF / rerank / MMR.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_FULL_PARAGRAPH_CHARS = 600


@dataclass
class ContextUnit:
    anchor: Dict[str, Any]
    mode: str
    sentences: List[Dict[str, Any]] = field(default_factory=list)
    text: str = ""
    paragraph_text: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sentence_id": self.anchor["sentence_id"],
            "para_id": self.anchor["para_id"],
            "paper_id": self.anchor["paper_id"],
            "anchor_text": self.anchor.get("text", ""),
            "anchor_score": self.anchor.get("score"),
            "context_mode": self.mode,
            "context_scored": False,
            "window_sentences": self.sentences,
            "text": self.text,
            "paragraph_text": self.paragraph_text,
        }


def build_context(
    anchor: Dict[str, Any],
    paragraph_sentences: List[Dict[str, Any]],
    *,
    window: int = 2,
    max_full_chars: int = MAX_FULL_PARAGRAPH_CHARS,
) -> ContextUnit:
    ordered = sorted(paragraph_sentences, key=lambda row: row.get("sequence") or 0)
    paragraph_text = " ".join((row.get("text") or "").strip() for row in ordered).strip()
    anchor_id = anchor["sentence_id"]
    anchor_index = next(
        (index for index, row in enumerate(ordered) if row["sentence_id"] == anchor_id),
        None,
    )
    if anchor_index is None:
        return ContextUnit(anchor=anchor, mode="anchor_only", sentences=[], text=anchor.get("text", ""), paragraph_text=paragraph_text)

    if len(paragraph_text) <= max_full_chars:
        selected = ordered
        mode = "full_paragraph"
    else:
        start = max(0, anchor_index - window)
        end = min(len(ordered), anchor_index + window + 1)
        selected = ordered[start:end]
        mode = "sentence_window"

    sentences = []
    for row in selected:
        sentences.append(
            {
                "sentence_id": row["sentence_id"],
                "text": row.get("text") or "",
                "is_anchor": row["sentence_id"] == anchor_id,
            }
        )
    return ContextUnit(
        anchor=anchor,
        mode=mode,
        sentences=sentences,
        text=" ".join(row["text"] for row in sentences).strip(),
        paragraph_text=paragraph_text,
    )
