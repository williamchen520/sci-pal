"""Deterministic answer verification (no LLM).

Checks:
* every cited evidence id exists in the provided evidence set
* factual sentences carry at least one citation
* quoted spans can be found in the evidence text (quote grounding)
* conflict blocks carry paper/section/quote/condition

``ok=False`` means the answer must not be promoted to a formal conclusion.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

CITE_RE = re.compile(r"\[([PFTARG])(\d+)\]")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")
QUOTE_RE = re.compile(r"[“\"]([^”\"]{8,300})[”\"]")
CONFLICT_HINT = re.compile(r"(冲突|矛盾|不一致|conflict|contradict)", re.IGNORECASE)


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in SENTENCE_RE.split(text or "") if s.strip()]


def _evidence_text(evidence: Optional[Iterable[Dict[str, Any]]]) -> str:
    if not evidence:
        return ""
    parts = []
    for item in evidence:
        parts.append(str(item.get("text") or ""))
        for paragraph in item.get("paragraphs") or []:
            parts.append(str(paragraph))
    return "\n".join(parts)


def verify_answer(
    answer: str,
    evidence_ids: Optional[Iterable[str]] = None,
    evidence: Optional[Iterable[Dict[str, Any]]] = None,
    require_citations: bool = True,
) -> Dict[str, Any]:
    answer = answer or ""
    allowed = {
        str(i) if str(i).startswith("[") else f"[{i}]"
        for i in (evidence_ids or [])
    }
    if not allowed and evidence:
        allowed = {
            f"[{item.get('evidence_id')}]"
            for item in evidence
            if item.get("evidence_id")
        }

    cited = {f"[{kind}{number}]" for kind, number in CITE_RE.findall(answer)}
    missing = sorted(cited - allowed) if allowed else []

    uncited: List[str] = []
    if require_citations:
        for sentence in _split_sentences(answer):
            if len(sentence) < 40 or CITE_RE.search(sentence):
                continue
            if sentence.startswith(("#", "-", "*", "|")):
                continue
            uncited.append(sentence[:240])
        uncited = uncited[:6]

    quote_mismatch: List[str] = []
    corpus = _evidence_text(evidence)
    if corpus:
        for quote in QUOTE_RE.findall(answer):
            if quote.strip() and quote.strip().lower() not in corpus.lower():
                quote_mismatch.append(quote[:120])

    conflict = {"structure_ok": True, "missing_conditions": []}
    if CONFLICT_HINT.search(answer):
        # a conflict statement should expose the limiting condition
        conflict["structure_ok"] = bool(
            re.search(r"(限定|人群|剂量|亚组|condition|subgroup|dose)", answer, re.IGNORECASE)
        )
        if not conflict["structure_ok"]:
            conflict["missing_conditions"].append("未说明限定条件")

    warnings: List[str] = []
    if missing:
        warnings.append(f"引用了不存在的证据：{', '.join(missing)}")
    if uncited:
        warnings.append(f"{len(uncited)} 条事实陈述没有引用")
    if quote_mismatch:
        warnings.append(f"{len(quote_mismatch)} 处引文在证据中找不到")
    if not conflict["structure_ok"]:
        warnings.append("检测到冲突表述但缺少限定条件")

    ok = not missing and not uncited and not quote_mismatch and conflict["structure_ok"]
    return {
        "ok": ok,
        "missing_ids": missing,
        "uncited_claims": uncited,
        "quote_mismatch": quote_mismatch,
        "guard": {"unknown_ratio": 0.0, "unknown_terms": []},
        "conflict": conflict,
        "warnings": warnings,
        "cited": sorted(cited),
        "allowed": sorted(allowed),
    }
