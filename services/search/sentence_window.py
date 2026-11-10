"""Logical sentence window.

The anchor sentence is the only ranked unit. Context is selected by a
configurable policy: logic words are pulled in unconditionally, low-relevance
neighbours are skipped, section/heading boundaries stop the scan, and the final
text is hard-capped.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY_PATH = ROOT / "config" / "context_policy.json"
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
DEFAULT_MAX_CHARS = 1200


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text or "") if len(token) > 1]


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    pattern = re.escape(phrase.strip())
    return re.search(rf"(?<![A-Za-z]){pattern}(?![A-Za-z])", text or "", re.IGNORECASE) is not None


def _is_heading(text: str, terms: Iterable[str]) -> bool:
    normalized = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", (text or "").strip().lower())
    normalized = normalized.strip(" .:;—-")
    return normalized in {term.lower().strip() for term in terms if term.strip()}


@dataclass
class WindowPolicy:
    max_chars: int = DEFAULT_MAX_CHARS
    max_scan: int = 6
    relevance_threshold: float = 0.2
    logic_terms: List[str] = field(default_factory=list)
    heading_terms: List[str] = field(default_factory=list)
    stopwords: List[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, path: Optional[str | Path] = None) -> "WindowPolicy":
        config_path = Path(path or os.environ.get("SCIPAL_CONTEXT_POLICY", DEFAULT_POLICY_PATH))
        data: Dict[str, Any] = {}
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        logic_terms = []
        for terms in (data.get("logic_terms") or {}).values():
            logic_terms.extend(terms)
        env_logic = os.environ.get("SCIPAL_CONTEXT_LOGIC_TERMS", "").strip()
        if env_logic:
            logic_terms = [term.strip() for term in env_logic.split(",") if term.strip()]
        return cls(
            max_chars=max(1, int(os.environ.get("SCIPAL_CONTEXT_MAX_CHARS", data.get("max_chars", DEFAULT_MAX_CHARS)))),
            max_scan=max(1, int(data.get("max_scan", 6))),
            relevance_threshold=float(data.get("relevance_threshold", 0.2)),
            logic_terms=logic_terms,
            heading_terms=list(data.get("heading_terms") or []),
            stopwords=list(data.get("stopwords") or []),
        )

    def is_logic(self, text: str) -> bool:
        return any(_contains_phrase(text, term) for term in self.logic_terms)

    def is_heading(self, text: str) -> bool:
        return _is_heading(text, self.heading_terms)

    def relevance(self, query: str, text: str) -> float:
        query_terms = {term for term in _tokens(query) if term not in self.stopwords}
        if not query_terms:
            return 0.0
        text_terms = {term for term in _tokens(text) if term not in self.stopwords}
        return len(query_terms & text_terms) / len(query_terms)


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
    query: str = "",
    policy: Optional[WindowPolicy] = None,
) -> ContextUnit:
    policy = policy or WindowPolicy.from_config()
    ordered = sorted(paragraph_sentences, key=lambda row: row.get("sequence") or 0)
    paragraph_text = " ".join((row.get("text") or "").strip() for row in ordered).strip()
    anchor_id = anchor["sentence_id"]
    anchor_index = next(
        (index for index, row in enumerate(ordered) if row["sentence_id"] == anchor_id),
        None,
    )
    if anchor_index is None:
        return ContextUnit(
            anchor=anchor,
            mode="anchor_only",
            sentences=[],
            text=(anchor.get("text") or "")[: policy.max_chars],
            paragraph_text=paragraph_text,
        )

    anchor_row = ordered[anchor_index]
    chosen: Dict[int, str] = {anchor_index: "anchor"}
    left_stop = right_stop = False

    for distance in range(1, policy.max_scan + 1):
        for side, index in (("left", anchor_index - distance), ("right", anchor_index + distance)):
            if index < 0 or index >= len(ordered):
                continue
            if (side == "left" and left_stop) or (side == "right" and right_stop):
                continue
            row = ordered[index]
            if row.get("section_id") and anchor_row.get("section_id") and row["section_id"] != anchor_row["section_id"]:
                if side == "left":
                    left_stop = True
                else:
                    right_stop = True
                continue
            if row.get("blank_before") or policy.is_heading(row.get("text", "")):
                if side == "left":
                    left_stop = True
                else:
                    right_stop = True
                continue
            if policy.is_logic(row.get("text", "")):
                chosen[index] = "logic"
            elif policy.relevance(query, row.get("text", "")) >= policy.relevance_threshold:
                chosen[index] = "relevant"

    selected_indices = sorted(chosen)
    selected: List[Dict[str, Any]] = []
    total = 0
    for index in selected_indices:
        row = ordered[index]
        text = (row.get("text") or "").strip()
        if not text:
            continue
        separator = 1 if total else 0
        if total + separator + len(text) > policy.max_chars:
            if index == anchor_index and not selected:
                text = text[: policy.max_chars]
            else:
                continue
        total += separator + len(text)
        selected.append(
            {
                "sentence_id": row["sentence_id"],
                "text": text,
                "is_anchor": index == anchor_index,
                "reason": chosen[index],
            }
        )

    if not selected:
        text = (anchor.get("text") or "")[: policy.max_chars]
        selected = [
            {
                "sentence_id": anchor_id,
                "text": text,
                "is_anchor": True,
                "reason": "anchor",
            }
        ]
    return ContextUnit(
        anchor=anchor,
        mode="logical_window",
        sentences=selected,
        text=" ".join(row["text"] for row in selected)[: policy.max_chars],
        paragraph_text=paragraph_text,
    )
