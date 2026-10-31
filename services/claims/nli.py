"""Claim-evidence relation classification.

LLM output is advisory. A ``refutes`` label is only accepted when the model
returns a direct contradiction rationale; otherwise the relation is downgraded
to ``underdetermines`` for human review.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

RELATIONS = {"supports", "refutes", "mentions", "underdetermines"}

SYSTEM_PROMPT = """你是科学论证的证据关系分类器。
给定一个 claim 和一条候选证据（原文引用），判断候选证据与 claim 的关系：
- supports：直接支持 claim 的核心断言；
- refutes：直接否定 claim 的核心断言，或报告方向相反的数值/结论；
- mentions：提到同一主题，但不支持也不否定；
- underdetermines：证据不足、限定条件不同、或无法判断。

必须区分：
1. 不同人群/剂量/终点/治疗线造成的异质性，不是 refutes；
2. 同一主题但不同结论，只有在同一限定条件下才可能是 refutes；
3. 只能依据给出的 quote，不得引入外部知识。

只返回 JSON：
{"relation":"supports|refutes|mentions|underdetermines","confidence":0.0,"reason":"一句话，必须引用限定条件或数值"}
"""


def _normalize(data: Any) -> Optional[Dict[str, Any]]:
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return None
    relation = str(data.get("relation") or "").strip().lower()
    if relation not in RELATIONS:
        return None
    try:
        confidence = float(data.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "relation": relation,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(data.get("reason") or "").strip()[:400],
    }


def classify(
    claim_text: str,
    quote: str,
    llm_client=None,
) -> Dict[str, Any]:
    if llm_client is None or not getattr(llm_client, "is_available", lambda: False)():
        return {
            "relation": "underdetermines",
            "confidence": 0.0,
            "reason": "LLM unavailable; manual review required",
        }
    user = f"CLAIM:\n{claim_text}\n\nEVIDENCE QUOTE:\n{quote}\n"
    try:
        raw = llm_client.chat_json(SYSTEM_PROMPT, user, temperature=0.0)
    except Exception as exc:  # noqa: BLE001 - advisory layer must not break API
        return {
            "relation": "underdetermines",
            "confidence": 0.0,
            "reason": f"LLM classification failed: {str(exc)[:160]}",
        }
    result = _normalize(raw)
    if not result:
        return {
            "relation": "underdetermines",
            "confidence": 0.0,
            "reason": "LLM returned an invalid relation",
        }
    if result["relation"] == "refutes" and not result["reason"]:
        result["relation"] = "underdetermines"
        result["confidence"] = 0.0
        result["reason"] = "refutes without a direct contradiction rationale"
    return result
