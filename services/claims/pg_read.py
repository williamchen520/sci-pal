"""PostgreSQL read adapter for claim cards (G3.5a)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from services.db.pg_pool import main_read_connection


def _card(row) -> Dict[str, Any]:
    card = dict(row)
    for key, default in (
        ("qualifiers_json", "{}"),
        ("corpus_json", "[]"),
        ("writing_brief", "{}"),
    ):
        raw = card.get(key)
        try:
            card[key.replace("_json", "") if key != "writing_brief" else key] = (
                json.loads(raw) if raw else json.loads(default)
            )
        except (TypeError, ValueError):
            card[key.replace("_json", "") if key != "writing_brief" else key] = json.loads(default)
    return card


def list_claims(limit: int = 50) -> List[Dict[str, Any]]:
    pg = main_read_connection()
    try:
        rows = pg.execute(
            "SELECT * FROM claim_cards ORDER BY updated_at DESC, claim_id LIMIT %s",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        pg.close()


def get_claim(claim_id: str) -> Optional[Dict[str, Any]]:
    pg = main_read_connection()
    try:
        card_row = pg.execute(
            "SELECT * FROM claim_cards WHERE claim_id = %s", (claim_id,)
        ).fetchone()
        if not card_row:
            return None
        card = _card(card_row)
        card["evidence"] = [
            dict(row)
            for row in pg.execute(
                "SELECT * FROM claim_card_evidence WHERE claim_id = %s "
                "ORDER BY relation, strength DESC",
                (claim_id,),
            ).fetchall()
        ]
        card["events"] = [
            dict(row)
            for row in pg.execute(
                "SELECT * FROM claim_card_events WHERE claim_id = %s "
                "ORDER BY created_at DESC LIMIT 20",
                (claim_id,),
            ).fetchall()
        ]
        return card
    finally:
        pg.close()
