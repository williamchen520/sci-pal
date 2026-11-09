"""Claim service facade (PostgreSQL only).

SQLite implementation lives in tests/support_sqlite_claims.py.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

RELATIONS = {"supports", "refutes", "mentions", "underdetermines"}
DECISIONS = {"accept", "revise", "reject", "contest"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event_row(claim_id: str, action: str, actor: str, note: str, now: str) -> dict:
    return {
        "event_id": f"evt_{hashlib.sha1((claim_id + action + now).encode()).hexdigest()[:12]}",
        "claim_id": claim_id,
        "action": action,
        "actor": actor,
        "note": note,
        "created_at": now,
    }


def connect(db_path=None):
    # Kept for call-site compatibility; storage is PostgreSQL-only.
    return None


def ensure_schema(db_path=None) -> None:
    return None


def list_claims(conn=None, limit: int = 50) -> List[Dict[str, Any]]:
    from services.claims import pg_read

    return pg_read.list_claims(limit)


def get_claim(conn=None, claim_id: str = "") -> Optional[Dict[str, Any]]:
    from services.claims import pg_read

    return pg_read.get_claim(claim_id)


def create_claim(conn=None, data: Optional[Dict[str, Any]] = None, actor: str = "human") -> str:
    from services.claims import pg_writes

    data = data or {}
    claim_id = data.get("claim_id") or "claim_" + hashlib.sha1(
        (data.get("claim_text") or "").encode("utf-8")
    ).hexdigest()[:12]
    now = _now()
    card = {
        "claim_id": claim_id,
        "workspace_id": data.get("workspace_id") or "ws_default",
        "title": data.get("title") or data.get("claim_text", "")[:80],
        "claim_text": data.get("claim_text") or "",
        "claim_type": data.get("claim_type") or "empirical",
        "status": data.get("status") or "draft",
        "confidence": float(data.get("confidence") or 0.0),
        "qualifiers_json": json.dumps(data.get("qualifiers") or {}, ensure_ascii=False),
        "corpus_json": json.dumps(data.get("corpus") or [], ensure_ascii=False),
        "warrant": data.get("warrant") or "",
        "backing": data.get("backing") or "",
        "rebuttal": data.get("rebuttal") or "",
        "strongest_counter": data.get("strongest_counter") or "",
        "writing_brief": json.dumps(data.get("writing_brief") or {}, ensure_ascii=False),
        "decision": data.get("decision") or "pending",
        "created_at": data.get("created_at") or now,
        "updated_at": now,
    }
    event = _event_row(claim_id, "create", actor, "", now)
    pg_writes.create_claim(card, event)
    return claim_id


def add_evidence(conn=None, claim_id: str = "", sentence_id: str = "", relation: str = "supports", rationale: str = "", strength: float = 0.5) -> Dict[str, Any]:
    from services.claims import pg_write

    return pg_write.add_evidence(
        claim_id, sentence_id, relation, rationale=rationale, strength=strength
    )


def add_note(conn=None, claim_id: str = "", note: str = "") -> Dict[str, Any]:
    from services.claims import pg_write

    return pg_write.add_note(claim_id, note)


def set_writing_brief(conn=None, claim_id: str = "", brief: Optional[Dict[str, Any]] = None, actor: str = "human") -> Dict[str, Any]:
    from services.claims import pg_read, pg_writes

    if not pg_read.get_claim(claim_id):
        raise ValueError("claim not found")
    now = _now()
    pg_writes.update_claim(
        claim_id,
        {"writing_brief": json.dumps(brief or {}, ensure_ascii=False), "updated_at": now},
        _event_row(claim_id, "writing_brief", actor, "", now),
    )
    return pg_read.get_claim(claim_id) or {}


def search_candidates(conn=None, claim_id: str = "", direction: str = "support", limit: int = 5) -> List[Dict[str, Any]]:
    from services.claims import pg_search

    return pg_search.search_candidates(claim_id, direction=direction, limit=limit)


def interrogate(conn=None, claim_id: str = "", direction: str = "support", use_llm: bool = False, llm_client=None, retriever=None, limit: int = 5) -> List[Dict[str, Any]]:
    from services.claims import pg_search

    return pg_search.interrogate(
        claim_id, direction=direction, use_llm=use_llm, llm_client=llm_client, retriever=retriever, limit=limit
    )


def decide(conn=None, claim_id: str = "", decision: str = "", note: str = "", actor: str = "human") -> Dict[str, Any]:
    from services.claims import pg_write

    return pg_write.decide(claim_id, decision, note=note, actor=actor)
