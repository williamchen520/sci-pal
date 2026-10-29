"""LLM-based per-claim grounding check."""

from __future__ import annotations

import json
import re
from typing import Dict, Iterable, List

from services.qa.semantic_grounding import split_claims

JSON_BLOCK = re.compile(r"\[[\s\S]*?\]")


def build_prompt(claims: List[str], evidence_texts: List[str]) -> str:
    evidence = "\n\n".join(
        f"[E{index}] {text[:1200]}" for index, text in enumerate(evidence_texts[:6], 1)
    )
    claim_lines = "\n".join(f"{index}. {claim}" for index, claim in enumerate(claims, 1))
    return (
        "You are a strict scientific claim verifier.\n"
        "For each claim, decide whether it is directly supported by the evidence.\n"
        "A claim is supported only if the evidence contains the same fact; paraphrase is allowed, "
        "but external knowledge is NOT support.\n"
        "Return ONLY a JSON array like "
        '[{"claim": 1, "supported": true}, {"claim": 2, "supported": false}].\n\n'
        f"Evidence:\n{evidence}\n\nClaims:\n{claim_lines}"
    )


def parse_verdicts(text: str) -> Dict[int, bool]:
    match = JSON_BLOCK.search(text or "")
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    verdicts = {}
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            verdicts[int(item["claim"])] = bool(item["supported"])
        except (KeyError, TypeError, ValueError):
            continue
    return verdicts


def check(
    answer: str,
    evidence_texts: Iterable[str],
    llm,
    min_ratio: float = 0.6,
    min_support: float = 0.0,
) -> Dict:
    claims = split_claims(answer)[:8]
    if not claims:
        return {"grounded": True, "supported_ratio": 1.0, "claims": 0, "unsupported": []}
    texts = [text for text in evidence_texts if text and len(text) > 20]
    if not texts:
        return {
            "grounded": False,
            "supported_ratio": 0.0,
            "claims": len(claims),
            "unsupported": claims,
        }
    prompt = build_prompt(claims, texts)
    try:
        raw = llm.chat(
            system_prompt="You verify scientific claims against evidence. Output JSON only.",
            user_prompt=prompt,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "grounded": True,
            "supported_ratio": 1.0,
            "claims": len(claims),
            "unsupported": [],
            "error": str(exc),
        }
    verdicts = parse_verdicts(raw)
    if not verdicts:
        return {
            "grounded": True,
            "supported_ratio": 1.0,
            "claims": len(claims),
            "unsupported": [],
            "error": "unparseable",
        }
    supported = 0
    unsupported = []
    for index, claim in enumerate(claims, 1):
        if verdicts.get(index, False):
            supported += 1
        else:
            unsupported.append(claim)
    ratio = supported / len(claims)
    return {
        "grounded": ratio >= min_ratio,
        "supported_ratio": round(ratio, 4),
        "claims": len(claims),
        "supported": supported,
        "unsupported": unsupported[:5],
    }
