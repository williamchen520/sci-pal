"""Flask adapter for the response contracts.

Registering the handlers is opt-in and idempotent; it does not change existing
routes until they start returning envelopes. Once registered, every failure
leaving the app has the same JSON shape and a stable HTTP status.
"""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .envelope import fail
from .errors import AppError, from_exception

logger = logging.getLogger(__name__)


def register_error_handlers(app: Flask) -> Flask:
    """Install AppError / HTTPException / Exception handlers on ``app``."""
    if app.extensions.get("contracts.handlers_installed"):
        return app

    @app.errorhandler(AppError)
    def _handle_app_error(exc: AppError):  # type: ignore[misc]
        return _respond(exc)

    @app.errorhandler(HTTPException)
    def _handle_http_error(exc: HTTPException):  # type: ignore[misc]
        return _respond(from_exception(exc))

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):  # type: ignore[misc]
        logger.exception("unhandled exception")
        return _respond(from_exception(exc))

    app.extensions["contracts.handlers_installed"] = True
    return app


def _respond(error: AppError) -> tuple[Any, int]:
    return jsonify(fail(error)), error.status
