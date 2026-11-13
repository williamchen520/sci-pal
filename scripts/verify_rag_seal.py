#!/usr/bin/env python3
"""Verify a SciPal RO-Crate seal without starting the API."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.rag_control.signing import verify


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package")
    args = parser.parse_args()
    with zipfile.ZipFile(args.package) as archive:
        try:
            final = json.loads(archive.read("data/finalization.json"))
            canonical = archive.read("data/canonical.json")
        except KeyError as exc:
            print(f"INVALID missing {exc}")
            return 1
    if not final:
        print("INVALID package is not finalized")
        return 1
    computed = hashlib.sha256(canonical).hexdigest()
    hash_ok = computed == final.get("content_hash")
    signature_ok = verify(
        final.get("content_hash", ""),
        final.get("signature", ""),
        final.get("public_key", ""),
    )
    print(
        json.dumps(
            {
                "content_hash_match": hash_ok,
                "signature_valid": signature_ok,
                "key_id": final.get("key_id"),
                "signed_at": final.get("signed_at"),
                "timestamp_source": final.get("timestamp_source"),
                "valid": bool(hash_ok and signature_ok),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if hash_ok and signature_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
