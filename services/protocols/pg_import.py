"""PostgreSQL protocol import (G3.10e2b)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping

from services.db.pg_pool import pg_connection
from services.protocols.service import (
    _duration,
    _first,
    _html_text,
    _normalize_protocol_id,
    _reagents,
    _text,
)


def _parse(payload: Mapping[str, Any], url: str = "") -> tuple[dict, list[dict]]:
    protocol = payload.get("protocol") if isinstance(payload.get("protocol"), Mapping) else payload
    protocol_id = _first(protocol, "id", "protocol_id", "guid") or _first(payload, "protocol_id")
    if not protocol_id:
        raise ValueError("payload has no protocol id")
    title = _first(protocol, "title", "name")
    try:
        doi = _first(protocol.get("doi") or {}, "doi") if isinstance(protocol.get("doi"), Mapping) else _text(protocol.get("doi"))
    except Exception:  # noqa: BLE001
        doi = ""
    steps = protocol.get("steps") or payload.get("steps") or []
    if isinstance(steps, Mapping):
        steps = steps.get("steps") or []
    parsed_steps = []
    for ordinal, step in enumerate(steps, 1):
        if not isinstance(step, Mapping):
            continue
        instructions = _html_text(
            _first(step, "step", "instructions", "description", "step_description", "text")
        )
        title_text = _first(step, "title", "name", "step_title", "section")
        if not title_text and instructions:
            title_text = instructions[:80]
        parsed_steps.append(
            {
                "step_id": _first(step, "id", "step_id", "guid") or f"{protocol_id}_step_{ordinal}",
                "ordinal": ordinal,
                "title": title_text,
                "instructions": instructions,
                "duration": _duration(_first(step, "duration", "time", "duration_text")),
                "reagents": _reagents(step),
            }
        )
    record = {
        "protocol_id": protocol_id,
        "title": title,
        "doi": doi,
        "version": _first(protocol, "version", "version_id", "v"),
        "url": url or _first(protocol, "url", "link"),
        "license": _first(protocol, "license", "license_name"),
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_json": json.dumps(payload, ensure_ascii=False),
    }
    return record, parsed_steps


def import_payload(payload: Mapping[str, Any], *, url: str = "") -> dict:
    record, steps = _parse(payload, url=url)
    pg = pg_connection()
    try:
        pg.execute(
            "INSERT INTO protocol_imports "
            "(protocol_id, title, doi, version, url, license, fetched_at, raw_json) "
            "VALUES (%(protocol_id)s, %(title)s, %(doi)s, %(version)s, %(url)s, "
            "%(license)s, %(fetched_at)s, %(raw_json)s) "
            "ON CONFLICT (protocol_id) DO UPDATE SET title=EXCLUDED.title, doi=EXCLUDED.doi, "
            "version=EXCLUDED.version, url=EXCLUDED.url, license=EXCLUDED.license, "
            "fetched_at=EXCLUDED.fetched_at, raw_json=EXCLUDED.raw_json",
            record,
        )
        pg.execute("DELETE FROM protocol_steps WHERE protocol_id = %s", (record["protocol_id"],))
        for step in steps:
            pg.execute(
                "INSERT INTO protocol_steps "
                "(step_id, protocol_id, ordinal, title, instructions, duration, reagents_json) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    step["step_id"], record["protocol_id"], step["ordinal"], step["title"],
                    step["instructions"], step["duration"],
                    json.dumps(step["reagents"], ensure_ascii=False),
                ),
            )
        pg.commit()
    finally:
        pg.close()
    return {
        "protocol_id": record["protocol_id"],
        "title": record["title"],
        "steps": len(steps),
    }


def import_protocol(protocol_id: str, client) -> dict:
    if client is None:
        raise RuntimeError("protocols.io client not configured")
    fetch = getattr(client, "fetch_protocol", None)
    if fetch is None:
        raise RuntimeError("client does not support fetch_protocol")
    normalized = _normalize_protocol_id(protocol_id)
    payload = fetch(normalized)
    return import_payload(
        payload,
        url=f"https://www.protocols.io/view/{normalized}",
    )
