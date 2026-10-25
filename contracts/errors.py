"""Stable error taxonomy for API and service boundaries.

Rules of the house:
- Business-level "not ideal" results are still successes at the HTTP layer
  (see ``contracts.envelope.ok``); this module is only for failures.
- Never leak internal exception text to the client. ``from_exception`` keeps
  the original exception on ``.cause`` for logging, but the payload carries a
  stable, human-readable message.
"""

from __future__ import annotations

import sqlite3
from enum import Enum
from typing import Any, Mapping


class ErrorKind(str, Enum):
    """Stable, machine-readable failure categories."""

    INVALID_INPUT = "invalid_input"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    UPSTREAM = "upstream"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


#: HTTP status for each kind, used by the Flask binding.
STATUS_BY_KIND: dict[ErrorKind, int] = {
    ErrorKind.INVALID_INPUT: 400,
    ErrorKind.NOT_FOUND: 404,
    ErrorKind.CONFLICT: 409,
    ErrorKind.FORBIDDEN: 403,
    ErrorKind.RATE_LIMITED: 429,
    ErrorKind.UPSTREAM: 502,
    ErrorKind.TIMEOUT: 504,
    ErrorKind.INTERNAL: 500,
}

#: Kinds worth retrying on the caller side.
RETRYABLE_KINDS = frozenset(
    {ErrorKind.RATE_LIMITED, ErrorKind.UPSTREAM, ErrorKind.TIMEOUT}
)


class AppError(Exception):
    """An expected failure with a stable kind and a client-safe message."""

    def __init__(
        self,
        kind: ErrorKind,
        message: str,
        *,
        source: str | None = None,
        retryable: bool | None = None,
        details: Mapping[str, Any] | None = None,
        status: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.source = source
        self.retryable = kind in RETRYABLE_KINDS if retryable is None else retryable
        self.details = dict(details) if details else {}
        self.status = status or STATUS_BY_KIND[kind]
        if cause is not None:
            self.__cause__ = cause

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.source:
            payload["source"] = self.source
        if self.details:
            payload["details"] = self.details
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"AppError({self.kind.value!r}, {self.message!r})"


class InvalidInput(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.INVALID_INPUT, message, **kwargs)


class NotFound(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.NOT_FOUND, message, **kwargs)


class Conflict(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.CONFLICT, message, **kwargs)


class Forbidden(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.FORBIDDEN, message, **kwargs)


class RateLimited(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.RATE_LIMITED, message, **kwargs)


class UpstreamError(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.UPSTREAM, message, **kwargs)


class UpstreamTimeout(AppError):
    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(ErrorKind.TIMEOUT, message, **kwargs)


class InternalError(AppError):
    def __init__(self, message: str = "Internal error", **kwargs: Any) -> None:
        super().__init__(ErrorKind.INTERNAL, message, **kwargs)


def from_exception(exc: BaseException) -> AppError:
    """Map an arbitrary exception to an ``AppError``.

    The original exception is preserved as ``__cause__`` so callers can log it;
    the returned error deliberately carries a generic message for unclassified
    failures.
    """
    if isinstance(exc, AppError):
        return exc

    # Werkzeug HTTP errors (abort(404), routing failures, ...) when available.
    try:  # pragma: no cover - import guarded for non-Flask use
        from werkzeug.exceptions import HTTPException, NotFound as WNotFound

        if isinstance(exc, WNotFound):
            return NotFound("Resource not found", cause=exc)
        if isinstance(exc, HTTPException):
            code = exc.code or 500
            kind = {
                400: ErrorKind.INVALID_INPUT,
                403: ErrorKind.FORBIDDEN,
                404: ErrorKind.NOT_FOUND,
                409: ErrorKind.CONFLICT,
                429: ErrorKind.RATE_LIMITED,
            }.get(code, ErrorKind.INTERNAL)
            return AppError(kind, exc.description or exc.name, status=code, cause=exc)
    except ImportError:
        pass

    if isinstance(exc, (TimeoutError,)):
        return UpstreamTimeout("Upstream request timed out", cause=exc)
    if isinstance(exc, (ValueError, TypeError)):
        return InvalidInput(str(exc), cause=exc)
    if isinstance(exc, sqlite3.OperationalError):
        return InternalError("Database temporarily unavailable", cause=exc)
    return InternalError("Internal error", cause=exc)
