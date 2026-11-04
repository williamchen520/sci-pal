"""PostgreSQL write adapter for claim evidence, decisions and notes."""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from services.claims import pg_read, pg_writes
from services.claims.service import DECISIONS, RELATIONS, _event_row, _now
from services.db.pg_pool import pg_connection


def _sentence(sentence_id: str):
    pg = pg_connection()
    try:
        row = pg.execute(
            "SELECT sentence_id, para_id, paper_id, text FROM sentences WHERE sentence_id = %s",
            (sentence_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        pg.close()


def add_evidence(
    claim_id: str,
    sentence_id: str,
    relation: str,
    *,
    rationale: str = "",
    strength: float = 0.5,
    actor: str = "human",
) -> Dict[str, Any]:
    if relation not in RELATIONS:
        raise ValueError("invalid relation")
    if not pg_read.get_claim(claim_id):
        raise ValueError("claim not found")
    sentence = _sentence(sentence_id)
    if not sentence:
        raise ValueError("sentence not found")
    now = _now()
    evidence_id = "cev_" + hashlib.sha1(
        f"{claim_id}:{sentence_id}:{relation}".encode()
    ).hexdigest()[:14]
    evidence = {
        "evidence_id": evidence_id,
        "claim_id": claim_id,
        "paper_id": sentence["paper_id"],
        "node_type": "sentence",
        "node_id": sentence_id,
        "relation": relation,
        "strength": float(strength),
        "quote": sentence["text"],
        "rationale": rationale,
        "source_type": "literature",
        "created_at": now,
    }
    event = {
        "event_id": "evt_" + hashlib.sha1(
            (claim_id + f"evidence:{relation}" + now).encode()
        ).hexdigest()[:12],
        "claim_id": claim_id,
        "action": f"evidence:{relation}",
        "actor": actor,
        "note": sentence_id,
        "created_at": now,
    }
    pg_writes.add_evidence(evidence, event)
    return pg_read.get_claim(claim_id) or {}


def decide(
    claim_id: str,
    decision: str,
    *,
    note: str = "",
    actor: str = "human",
) -> Dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError("invalid decision")
    if not pg_read.get_claim(claim_id):
        raise ValueError("claim not found")
    status = {
        "accept": "accepted",
        "revise": "revised",
        "reject": "rejected",
        "contest": "contested",
    }[decision]
    now = _now()
    fields = {
        "status": status,
        "decision": decision,
        "decision_note": note,
        "decided_by": actor,
        "decided_at": now,
        "updated_at": now,
    }
    pg_writes.update_claim(claim_id, fields, _event_row(claim_id, f"decision:{decision}", actor, note, now))
    return pg_read.get_claim(claim_id) or {}


def add_note(claim_id: str, note: str, *, actor: str = "human") -> Dict[str, Any]:
    if not pg_read.get_claim(claim_id):
        raise ValueError("claim not found")
    now = _now()
    pg_writes.update_claim(
        claim_id,
        {"updated_at": now},
        _event_row(claim_id, "review_note", actor, note, now),
    )
    return pg_read.get_claim(claim_id) or {}
