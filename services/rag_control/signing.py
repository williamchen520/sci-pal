"""R14: local Ed25519 seal signatures.

This is a real asymmetric signature over the content hash, but the timestamp is
local clock time, not an external RFC 3161 timestamp authority.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

KEY_PATH = Path(os.environ.get("SCIPAL_RAG_SIGNING_KEY", r"G:/runs/rag_signing_key.pem"))


def _load_or_create() -> Ed25519PrivateKey:
    if KEY_PATH.exists():
        return serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(KEY_PATH, 0o600)
    except OSError:
        pass
    return key


def sign(content_hash: str) -> dict[str, str]:
    key = _load_or_create()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signature = key.sign(content_hash.encode("utf-8"))
    return {
        "algorithm": "ed25519",
        "signature": base64.b64encode(signature).decode("ascii"),
        "public_key": base64.b64encode(public).decode("ascii"),
        "key_id": hashlib.sha256(public).hexdigest()[:16],
    }


def verify(content_hash: str, signature: str, public_key: str) -> bool:
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key))
        key.verify(base64.b64decode(signature), content_hash.encode("utf-8"))
        return True
    except Exception:  # noqa: BLE001
        return False
