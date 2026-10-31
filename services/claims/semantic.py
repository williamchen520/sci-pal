"""Semantic opposition query generation and paragraph-to-sentence expansion."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

REFUTE_SYSTEM = """你是科学论证的反对证据检索助手。
给定 claim 与限定条件，生成 3 条英文检索式，分别寻找：
1. 直接否定该 claim 的结果；
2. 同一人群/干预下更差或无效的结果；
3. 边界条件、耐药或方法学反例。
只返回 JSON 字符串数组，不要解释。"""

STOP = {"the", "and", "for", "with", "from", "that", "this", "are", "was", "were"}


def _tokens(text: str) -> List[str]:
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", text or "")
        if len(token) >= 2 and token.lower() not in STOP
    ]


def fallback_queries(claim_text: str, qualifiers: Dict[str, Any] | None = None) -> List[str]:
    values = []
    if isinstance(qualifiers, dict):
        for value in qualifiers.values():
            if isinstance(value, (list, tuple)):
                values.extend(str(item) for item in value)
            else:
                values.append(str(value))
    base = " ".join(_tokens(" ".join(values))) or " ".join(_tokens(claim_text)[:8])
    if not base:
        return []
    return [
        f"{base} did not improve overall survival",
        f"{base} no significant benefit inferior outcome",
        f"{base} resistance limited response subgroup",
    ]


def generate_refute_queries(
    claim_text: str,
    qualifiers: Dict[str, Any] | None = None,
    llm_client=None,
    limit: int = 3,
) -> List[str]:
    if llm_client is not None and getattr(llm_client, "is_available", lambda: False)():
        user = f"CLAIM:\n{claim_text}\nQUALIFIERS:\n{qualifiers or {}}\n"
        try:
            raw = llm_client.chat_json(REFUTE_SYSTEM, user, temperature=0.0)
            if isinstance(raw, dict):
                raw = raw.get("queries") or []
            queries = [str(item).strip() for item in raw if str(item).strip()]
            if queries:
                return queries[:limit]
        except Exception:  # noqa: BLE001 - fallback is intentional
            pass
    return fallback_queries(claim_text, qualifiers)[:limit]


def _overlap(claim_text: str, sentence: str) -> float:
    wanted = set(_tokens(claim_text))
    if not wanted:
        return 0.0
    return len(wanted & set(_tokens(sentence))) / len(wanted)


def semantic_candidates(
    conn,
    retriever,
    claim_text: str,
    qualifiers: Dict[str, Any] | None,
    corpus: Iterable[str],
    queries: Iterable[str],
    limit: int = 8,
) -> List[Dict[str, Any]]:
    if retriever is None:
        return []
    allowed = set(corpus or [])
    rows: List[Dict[str, Any]] = []
    seen = set()
    for query in queries:
        try:
            env = retriever.retrieve(
                query,
                top_paragraphs=5,
                top_figures=0,
                top_tables=0,
                top_papers=0,
                allowed_paper_ids=allowed or None,
            )
        except Exception:  # noqa: BLE001 - semantic recall is optional
            continue
        for paragraph in env.get("paragraphs") or []:
            para_id = paragraph.get("para_id") or paragraph.get("paragraph_id")
            if not para_id:
                continue
            sentences = conn.execute(
                "SELECT sentence_id, paper_id, text AS quote FROM sentences "
                "WHERE para_id = ? ORDER BY rowid",
                (para_id,),
            ).fetchall()
            if not sentences:
                continue
            best = max(
                (dict(row) for row in sentences),
                key=lambda item: _overlap(claim_text, item["quote"]),
            )
            if best["sentence_id"] in seen:
                continue
            seen.add(best["sentence_id"])
            title = conn.execute(
                "SELECT title FROM papers WHERE paper_id = ?", (best["paper_id"],)
            ).fetchone()
            best["paper_title"] = title[0] if title else best["paper_id"]
            best["retrieval"] = "semantic"
            best["semantic_query"] = query
            rows.append(best)
            if len(rows) >= limit * 2:
                return rows
    return rows
