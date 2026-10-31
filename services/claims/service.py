"""Claim pilot service: cards, evidence anchors and human decisions."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from build_db.claim_pilot_schema import migrate

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "research.db"
TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]")
STOP = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "were",
    "has", "have", "had", "not", "but", "into", "than", "using", "study", "patients",
    "patient", "hcc", "hepatocellular", "carcinoma", "results", "conclusion",
}
RELATIONS = {"supports", "refutes", "mentions", "underdetermines"}
DECISIONS = {"accept", "revise", "reject", "contest"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _row(row) -> Optional[Dict[str, Any]]:
    return dict(row) if row else None


def _keywords(text: str, limit: int = 8) -> List[str]:
    seen = []
    for token in TOKEN_RE.findall(text or ""):
        low = token.lower()
        if len(low) < 3 or low in STOP or low in seen:
            continue
        seen.append(low)
        if len(seen) >= limit:
            break
    return seen


def list_claims(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM claim_cards ORDER BY updated_at DESC, claim_id LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def get_claim(conn: sqlite3.Connection, claim_id: str) -> Optional[Dict[str, Any]]:
    card = _row(conn.execute("SELECT * FROM claim_cards WHERE claim_id = ?", (claim_id,)).fetchone())
    if not card:
        return None
    evidence = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM claim_card_evidence WHERE claim_id = ? ORDER BY relation, strength DESC",
            (claim_id,),
        )
    ]
    events = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM claim_card_events WHERE claim_id = ? ORDER BY created_at DESC LIMIT 20",
            (claim_id,),
        )
    ]
    card["qualifiers"] = json.loads(card.get("qualifiers_json") or "{}")
    card["corpus"] = json.loads(card.get("corpus_json") or "[]")
    try:
        card["writing_brief"] = json.loads(card.get("writing_brief") or "{}")
    except (TypeError, ValueError):
        card["writing_brief"] = {}
    card["evidence"] = evidence
    card["events"] = events
    return card


def create_claim(conn: sqlite3.Connection, data: Dict[str, Any], actor: str = "human") -> str:
    claim_id = data.get("claim_id") or "claim_" + hashlib.sha1(
        (data.get("claim_text") or "").encode("utf-8")
    ).hexdigest()[:12]
    conn.execute(
        "INSERT OR REPLACE INTO claim_cards "
        "(claim_id, workspace_id, title, claim_text, claim_type, status, confidence, "
        "qualifiers_json, corpus_json, warrant, backing, rebuttal, strongest_counter, "
        "writing_brief, decision, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            claim_id,
            data.get("workspace_id") or "ws_default",
            data.get("title") or data.get("claim_text", "")[:80],
            data.get("claim_text") or "",
            data.get("claim_type") or "empirical",
            data.get("status") or "draft",
            float(data.get("confidence") or 0.0),
            json.dumps(data.get("qualifiers") or {}, ensure_ascii=False),
            json.dumps(data.get("corpus") or [], ensure_ascii=False),
            data.get("warrant") or "",
            data.get("backing") or "",
            data.get("rebuttal") or "",
            data.get("strongest_counter") or "",
            json.dumps(data.get("writing_brief") or {}, ensure_ascii=False),
            data.get("decision") or "pending",
            data.get("created_at") or _now(),
            _now(),
        ),
    )
    _event(conn, claim_id, "create", actor, "")
    conn.commit()
    return claim_id


def _event(conn, claim_id: str, action: str, actor: str = "human", note: str = "") -> None:
    conn.execute(
        "INSERT INTO claim_card_events (event_id, claim_id, action, actor, note) VALUES (?, ?, ?, ?, ?)",
        (f"evt_{hashlib.sha1((claim_id+action+_now()).encode()).hexdigest()[:12]}", claim_id, action, actor, note),
    )


def _sentence(conn, sentence_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT s.sentence_id, s.paper_id, s.text, p.title "
        "FROM sentences s JOIN papers p ON p.paper_id = s.paper_id WHERE s.sentence_id = ?",
        (sentence_id,),
    ).fetchone()
    return dict(row) if row else None


def add_evidence(
    conn: sqlite3.Connection,
    claim_id: str,
    sentence_id: str,
    relation: str,
    rationale: str = "",
    strength: float = 0.5,
    actor: str = "human",
) -> Dict[str, Any]:
    if relation not in RELATIONS:
        raise ValueError("invalid relation")
    claim = get_claim(conn, claim_id)
    if not claim:
        raise ValueError("claim not found")
    sentence = _sentence(conn, sentence_id)
    if not sentence:
        raise ValueError("sentence not found")
    evidence_id = "cev_" + hashlib.sha1(
        f"{claim_id}:{sentence_id}:{relation}".encode()
    ).hexdigest()[:14]
    conn.execute(
        "INSERT OR REPLACE INTO claim_card_evidence "
        "(evidence_id, claim_id, paper_id, node_type, node_id, relation, strength, quote, rationale, source_type) "
        "VALUES (?, ?, ?, 'sentence', ?, ?, ?, ?, ?, 'literature')",
        (
            evidence_id, claim_id, sentence["paper_id"], sentence_id, relation,
            float(strength), sentence["text"], rationale,
        ),
    )
    _event(conn, claim_id, f"evidence:{relation}", actor, sentence_id)
    conn.commit()
    return {
        "evidence_id": evidence_id,
        "claim_id": claim_id,
        "sentence_id": sentence_id,
        "paper_id": sentence["paper_id"],
        "quote": sentence["text"],
        "relation": relation,
    }


def search_candidates(
    conn: sqlite3.Connection,
    claim_id: str,
    direction: str = "support",
    limit: int = 8,
    retriever=None,
    llm_client=None,
) -> List[Dict[str, Any]]:
    claim = get_claim(conn, claim_id)
    if not claim:
        raise ValueError("claim not found")
    from services.claims import retrieval

    queries = retrieval.build_queries(claim["claim_text"], claim.get("qualifiers") or {})
    query = queries.get("refute" if direction == "oppose" else "support") or queries["support"]
    if not query:
        return []
    corpus = [paper_id for paper_id in (claim.get("corpus") or []) if paper_id]
    sql = (
        "SELECT s.sentence_id, s.paper_id, s.text AS quote, p.title AS paper_title "
        "FROM sentences_fts f JOIN sentences s ON s.rowid = f.rowid "
        "JOIN papers p ON p.paper_id = s.paper_id "
        "WHERE sentences_fts MATCH ?"
    )
    params: List[Any] = [query]
    if corpus:
        sql += f" AND s.paper_id IN ({','.join('?' * len(corpus))})"
        params.extend(corpus)
    sql += " LIMIT ?"
    params.append(max(limit * 4, limit))
    rows = conn.execute(sql, params).fetchall()
    candidates = [{**dict(row), "retrieval": "fts"} for row in rows]

    if direction == "oppose" and retriever is not None:
        from services.claims import semantic

        generated = semantic.generate_refute_queries(
            claim["claim_text"], claim.get("qualifiers") or {}, llm_client=llm_client
        )
        semantic_rows = semantic.semantic_candidates(
            conn,
            retriever,
            claim["claim_text"],
            claim.get("qualifiers") or {},
            corpus,
            generated,
            limit=limit,
        )
        seen = {candidate["sentence_id"] for candidate in candidates}
        for candidate in semantic_rows:
            if candidate["sentence_id"] not in seen:
                candidates.append(candidate)
                seen.add(candidate["sentence_id"])

    ranked = retrieval.rank_candidates(
        claim["claim_text"],
        claim.get("qualifiers") or {},
        candidates,
        direction=direction,
    )
    for candidate in ranked:
        candidate["direction"] = direction
        candidate["query"] = query
    return ranked[:limit]


def add_note(
    conn: sqlite3.Connection,
    claim_id: str,
    note: str,
    actor: str = "human",
) -> Dict[str, Any]:
    claim = get_claim(conn, claim_id)
    if not claim:
        raise ValueError("claim not found")
    _event(conn, claim_id, "review_note", actor, note)
    conn.execute(
        "UPDATE claim_cards SET updated_at = ? WHERE claim_id = ?", (_now(), claim_id)
    )
    conn.commit()
    return get_claim(conn, claim_id) or {}


def set_writing_brief(
    conn: sqlite3.Connection,
    claim_id: str,
    brief: Dict[str, Any],
    actor: str = "human",
) -> Dict[str, Any]:
    claim = get_claim(conn, claim_id)
    if not claim:
        raise ValueError("claim not found")
    conn.execute(
        "UPDATE claim_cards SET writing_brief = ?, updated_at = ? WHERE claim_id = ?",
        (json.dumps(brief, ensure_ascii=False), _now(), claim_id),
    )
    _event(conn, claim_id, "writing_brief", actor, "")
    conn.commit()
    return get_claim(conn, claim_id) or {}


def interrogate(
    conn: sqlite3.Connection,
    claim_id: str,
    direction: str = "support",
    use_llm: bool = False,
    llm_client=None,
    retriever=None,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    claim = get_claim(conn, claim_id)
    if not claim:
        raise ValueError("claim not found")
    candidates = search_candidates(
        conn,
        claim_id,
        direction=direction,
        limit=limit,
        retriever=retriever,
        llm_client=llm_client,
    )
    if use_llm:
        from services.claims import nli

        for candidate in candidates:
            result = nli.classify(claim["claim_text"], candidate["quote"], llm_client)
            candidate.update(
                {
                    "suggested_relation": result["relation"],
                    "confidence": result["confidence"],
                    "reason": result["reason"],
                }
            )
    else:
        for candidate in candidates:
            candidate.update(
                {
                    "suggested_relation": "underdetermines",
                    "confidence": 0.0,
                    "reason": "LLM classification disabled",
                }
            )
    return candidates


def decide(
    conn: sqlite3.Connection,
    claim_id: str,
    decision: str,
    note: str = "",
    actor: str = "human",
) -> Dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError("invalid decision")
    claim = get_claim(conn, claim_id)
    if not claim:
        raise ValueError("claim not found")
    status = {
        "accept": "accepted",
        "revise": "revised",
        "reject": "rejected",
        "contest": "contested",
    }[decision]
    conn.execute(
        "UPDATE claim_cards SET status = ?, decision = ?, decision_note = ?, decided_by = ?, "
        "decided_at = ?, updated_at = ? WHERE claim_id = ?",
        (status, decision, note, actor, _now(), _now(), claim_id),
    )
    _event(conn, claim_id, f"decision:{decision}", actor, note)
    conn.commit()
    return get_claim(conn, claim_id) or {}


def ensure_schema(db_path: Path | str = DEFAULT_DB) -> None:
    migrate(db_path)
