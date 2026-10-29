"""Check the configured LLM provider (cloud or local).

Usage:
    python scripts/check_llm_provider.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.review.llm_client import create_llm_client


def main() -> int:
    provider = os.environ.get("SCIPAL_LLM_PROVIDER", "ollama")
    base_url = os.environ.get("SCIPAL_LLM_BASE_URL", "")
    model = os.environ.get("SCIPAL_LLM_MODEL", "")
    has_key = bool(
        os.environ.get("SCIPAL_LLM_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )
    print({"provider": provider, "base_url": base_url, "model": model, "has_key": has_key})
    if provider == "openai" and not has_key:
        print("missing SCIPAL_LLM_API_KEY; cannot call cloud model")
        return 2
    client = create_llm_client()
    try:
        answer = client.chat(
            system_prompt="Reply with exactly: pong",
            user_prompt="ping",
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"provider call failed: {exc}")
        return 1
    print({"ok": True, "answer": answer[:80]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
