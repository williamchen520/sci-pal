"""H4: classify Cell/JS/Cloudflare HTML responses without bypassing access control."""

from __future__ import annotations

import re
from typing import Any

import requests


class HtmlAccessError(RuntimeError):
    """The URL cannot be parsed as article HTML."""


class HtmlBlocked(HtmlAccessError):
    pass


class HtmlJsRequired(HtmlAccessError):
    pass


class HtmlPaywalled(HtmlAccessError):
    pass


class HtmlEmpty(HtmlAccessError):
    pass


BLOCK_MARKERS = (
    "just a moment",
    "cf-chl",
    "attention required",
    "cloudflare",
    "access denied",
)
PAYWALL_MARKERS = (
    "subscribe to continue",
    "purchase access",
    "access options",
    "sign in to view",
)
JS_MARKERS = (
    "enable javascript",
    "javascript is disabled",
    "requires javascript",
)


def _text(body: bytes | str) -> str:
    value = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    return re.sub(r"\s+", " ", value or "").lower()


def classify_html_response(status: int, body: bytes | str) -> str:
    text = _text(body)
    if status in {401, 402, 403}:
        return "blocked"
    if not text.strip():
        return "empty"
    if any(marker in text for marker in PAYWALL_MARKERS):
        return "paywalled"
    if any(marker in text for marker in BLOCK_MARKERS):
        return "blocked"
    if any(marker in text for marker in JS_MARKERS):
        return "js_required"
    return "ok"


def assert_html_access(status: int, body: bytes | str, *, url: str = "") -> None:
    state = classify_html_response(status, body)
    if state == "ok":
        return
    labels = {
        "blocked": "blocked by access control",
        "js_required": "requires JavaScript rendering",
        "paywalled": "paywall detected",
        "empty": "empty response",
    }
    message = f"{labels.get(state, state)}: {url}".strip()
    if state == "blocked":
        raise HtmlBlocked(message)
    if state == "js_required":
        raise HtmlJsRequired(message)
    if state == "paywalled":
        raise HtmlPaywalled(message)
    raise HtmlEmpty(message)


def fetch_html(url: str, *, timeout: float = 30.0, headers: dict[str, str] | None = None) -> str:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": "SciPal/1.0 (open-access research ingestion)",
            **(headers or {}),
        },
    )
    assert_html_access(response.status_code, response.content, url=url)
    return response.text
