"""Sentence-role scoring for anchor selection."""

from __future__ import annotations

import re
from typing import Iterable, Optional

from services.search.section_types import query_intent

NUMERIC = re.compile(
    r"\d+(\.\d+)?\s*%|p\s*[<=>]\s*0?\.\d+|\b(hr|or|rr|ci)\b\s*[=:]|\bn\s*=\s*\d+|"
    r"\d+(\.\d+)?\s*(mg|ml|gy|months?|years?|weeks?|days?)",
    re.I,
)
RESULT = re.compile(
    r"response|survival|efficacy|outcome|increase|decrease|improve|associated|"
    r"compared|we found|result|rate|median|hazard|reduction",
    re.I,
)
METHOD = re.compile(
    r"we (treated|enrolled|randomized|included)|randomized|patients were|"
    r"inclusion|exclusion|protocol|dose",
    re.I,
)
LIMITATION = re.compile(r"limitation|however|in contrast|controvers|small sample|bias", re.I)
BACKGROUND = re.compile(r"is a|are a|has been|known|defined as|background", re.I)


def classify_sentence(text: str) -> str:
    content = text or ""
    if LIMITATION.search(content):
        return "limitation"
    if METHOD.search(content) and not RESULT.search(content):
        return "method"
    if NUMERIC.search(content) or RESULT.search(content):
        return "result"
    if BACKGROUND.search(content):
        return "background"
    return "other"


def score_sentence(text: str, query_tokens: Iterable[str], intent: str) -> float:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text or "") if len(token) > 1}
    overlap = len(set(query_tokens) & tokens)
    role = classify_sentence(text)
    bonus = 0.0
    if intent == "results":
        bonus = {"result": 2.0, "method": 0.5, "limitation": 0.5}.get(role, 0.0)
    elif intent == "methods":
        bonus = {"method": 2.0, "result": 0.5}.get(role, 0.0)
    elif intent == "discussion":
        bonus = {"limitation": 2.0, "result": 0.5}.get(role, 0.0)
    if NUMERIC.search(text or ""):
        bonus += 0.5
    return overlap * 2.0 + bonus


def pick_anchor(sentences: list[dict], query: Optional[str]) -> Optional[dict]:
    if not sentences:
        return None
    if not query:
        return sentences[0]
    query_tokens = {
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", query)
        if len(token) > 1
    }
    intent = query_intent(query)
    return max(
        sentences,
        key=lambda sentence: score_sentence(sentence.get("text", ""), query_tokens, intent),
    )
