"""PostgreSQL-primary claim card writes (Phase 2, opt-in)."""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger(__name__)


class ClaimWriteError(RuntimeError):
    pass


def enabled() -> bool:
    backend = os.environ.get("SCIPAL_CLAIM_WRITE_BACKEND", "").strip().lower()
    return backend in {"postgres", "postgresql", "pg", "1", "true"} and bool(
        os.environ.get("SCIPAL_PG_DSN", "").strip()
    )


def _pg():
    from services.db.pg_pool import pg_connection
    from services.db.tenant_pilot import set_search_path

    pg = pg_connection(os.environ["SCIPAL_PG_DSN"])
    set_search_path(pg, "claims")
    return pg


def create_claim(card: dict, event: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO claim_cards "
                "(claim_id, workspace_id, title, claim_text, claim_type, status, confidence, "
                "qualifiers_json, corpus_json, warrant, backing, rebuttal, strongest_counter, "
                "writing_brief, decision, created_at, updated_at) "
                "VALUES (%(claim_id)s, %(workspace_id)s, %(title)s, %(claim_text)s, %(claim_type)s, "
                "%(status)s, %(confidence)s, %(qualifiers_json)s, %(corpus_json)s, %(warrant)s, "
                "%(backing)s, %(rebuttal)s, %(strongest_counter)s, %(writing_brief)s, "
                "%(decision)s, %(created_at)s, %(updated_at)s) "
                "ON CONFLICT (claim_id) DO UPDATE SET "
                "title=EXCLUDED.title, claim_text=EXCLUDED.claim_text, claim_type=EXCLUDED.claim_type, "
                "status=EXCLUDED.status, confidence=EXCLUDED.confidence, "
                "qualifiers_json=EXCLUDED.qualifiers_json, corpus_json=EXCLUDED.corpus_json, "
                "warrant=EXCLUDED.warrant, backing=EXCLUDED.backing, rebuttal=EXCLUDED.rebuttal, "
                "strongest_counter=EXCLUDED.strongest_counter, writing_brief=EXCLUDED.writing_brief, "
                "decision=EXCLUDED.decision, updated_at=EXCLUDED.updated_at",
                card,
            )
            pg.execute(
                "INSERT INTO claim_card_events (event_id, claim_id, action, actor, note, created_at) "
                "VALUES (%(event_id)s, %(claim_id)s, %(action)s, %(actor)s, %(note)s, %(created_at)s)",
                event,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG claim create failed; refusing SQLite fallback: %s", exc)
        raise ClaimWriteError("claim write backend unavailable") from exc


def add_evidence(evidence: dict, event: dict) -> None:
    try:
        with _pg() as pg:
            pg.execute(
                "INSERT INTO claim_card_evidence "
                "(evidence_id, claim_id, paper_id, node_type, node_id, relation, strength, quote, "
                "rationale, source_type, created_at) "
                "VALUES (%(evidence_id)s, %(claim_id)s, %(paper_id)s, %(node_type)s, %(node_id)s, "
                "%(relation)s, %(strength)s, %(quote)s, %(rationale)s, %(source_type)s, %(created_at)s) "
                "ON CONFLICT (evidence_id) DO UPDATE SET "
                "strength=EXCLUDED.strength, quote=EXCLUDED.quote, rationale=EXCLUDED.rationale",
                evidence,
            )
            pg.execute(
                "INSERT INTO claim_card_events (event_id, claim_id, action, actor, note, created_at) "
                "VALUES (%(event_id)s, %(claim_id)s, %(action)s, %(actor)s, %(note)s, %(created_at)s)",
                event,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG claim evidence failed; refusing SQLite fallback: %s", exc)
        raise ClaimWriteError("claim write backend unavailable") from exc


def update_claim(claim_id: str, fields: dict, event: dict) -> None:
    assignments = ", ".join(f"{key} = %s" for key in fields)
    try:
        with _pg() as pg:
            row = pg.execute(
                f"UPDATE claim_cards SET {assignments} WHERE claim_id = %s RETURNING claim_id",
                [*fields.values(), claim_id],
            ).fetchone()
            if not row:
                raise ClaimWriteError("claim not found in PostgreSQL")
            pg.execute(
                "INSERT INTO claim_card_events (event_id, claim_id, action, actor, note, created_at) "
                "VALUES (%(event_id)s, %(claim_id)s, %(action)s, %(actor)s, %(note)s, %(created_at)s)",
                event,
            )
    except ClaimWriteError:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("PG claim update failed; refusing SQLite fallback: %s", exc)
        raise ClaimWriteError("claim write backend unavailable") from exc
