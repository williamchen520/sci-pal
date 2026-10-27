"""Short-lived signed URLs for browser-loaded PDFs (viewer)."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

DEFAULT_SECRET = "scipal-dev-secret"


def _secret() -> bytes:
    return os.environ.get("SCIPAL_URL_SECRET", DEFAULT_SECRET).encode("utf-8")


def sign_path(path: str, expires_in: int = 600) -> str:
    expires = int(time.time()) + int(expires_in)
    signature = hmac.new(
        _secret(), f"{path}:{expires}".encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    return f"{path}?token={signature}&expires={expires}"


def verify_path(path: str, token: Optional[str], expires: Optional[str]) -> bool:
    if not token or not expires:
        return False
    try:
        expires_int = int(expires)
    except (TypeError, ValueError):
        return False
    if expires_int < int(time.time()):
        return False
    expected = hmac.new(
        _secret(), f"{path}:{expires_int}".encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    return hmac.compare_digest(expected, token)
