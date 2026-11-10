"""Shared experiment model helpers."""

from __future__ import annotations

import hashlib
import json

STATUSES = ("planned", "running", "completed", "failed", "abandoned")


class ProtocolNotFound(ValueError):
    pass


def _snapshot(row) -> dict:
    return {
        "title": row["title"],
        "status": row["status"],
        "protocol_id": row["protocol_id"],
        "protocol_version": row["protocol_version"],
        "content": row["content"],
    }


def _revision_hash(snapshot: dict) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_password(*args, **kwargs):
    from services.tenancy.pg_service import verify_password as _verify

    return _verify(*args, **kwargs)
