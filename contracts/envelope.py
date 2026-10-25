"""One response shape for every boundary (HTTP now, MCP/CLI later).

``ok`` and ``fail`` return plain dicts so they can be JSON-serialized by Flask,
by the MCP bridge, or by the CLI without a shared dependency.
"""

from __future__ import annotations

from typing import Any, Mapping

from .errors import AppError, ErrorKind

SCHEMA_VERSION = "1"


def ok(data: Any = None, **context: Any) -> dict[str, Any]:
    """Success envelope. ``data`` may be null when the operation is a side effect."""
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "data": data,
        "error": None,
        "context": _clean(context),
    }


def fail(error: AppError | Mapping[str, Any], **context: Any) -> dict[str, Any]:
    """Failure envelope.

    Accepts an ``AppError`` or an already-built error payload (e.g. one coming
    back from ``AppError.to_payload``). Unknown kinds are rejected early so a
    typo cannot silently become a 200.
    """
    if isinstance(error, AppError):
        payload = error.to_payload()
    elif isinstance(error, Mapping):
        payload = dict(error)
        kind = payload.get("kind")
        if kind not in {k.value for k in ErrorKind}:
            raise ValueError(f"Unknown error kind: {kind!r}")
        payload.setdefault("message", "Error")
        payload.setdefault("retryable", False)
    else:  # pragma: no cover - defensive
        raise TypeError(f"fail() expects AppError or mapping, got {type(error)!r}")

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "data": None,
        "error": payload,
        "context": _clean(context),
    }


def is_ok(envelope: Mapping[str, Any]) -> bool:
    return bool(envelope.get("ok"))


def _clean(context: Mapping[str, Any]) -> dict[str, Any]:
    """Drop empty context values so responses stay small and diffable."""
    return {key: value for key, value in context.items() if value is not None}
