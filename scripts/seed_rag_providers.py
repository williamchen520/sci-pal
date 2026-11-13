#!/usr/bin/env python3
"""Register RAG provider manifests in scipal_core."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.rag_control.registry import seed


def main() -> int:
    count = seed()
    print(f"RAG_PROVIDERS_SEEDED count={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
