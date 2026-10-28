"""LLM-enriched section summaries (optional, local Ollama)."""

from __future__ import annotations

import json
import urllib.request
from typing import Callable, Optional


def _call_ollama(model: str, prompt: str, host: str = "http://127.0.0.1:11434") -> str:
    payload = json.dumps(
        {
            "model": model,
            "stream": False,
            "options": {"temperature": 0.1},
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read())
    return (data.get("message") or {}).get("content", "")


def summarize(
    title: str,
    text: str,
    model: str = "qwen2.5:3b",
    llm: Optional[Callable[[str], str]] = None,
) -> str:
    prompt = (
        "Summarize the following section in 2 concise sentences. Keep numbers and "
        "clinical claims exact; do not add information.\n"
        f"Section: {title}\nText: {text[:1500]}\nSummary:"
    )
    try:
        raw = llm(text) if llm else _call_ollama(model, prompt)
    except Exception:  # noqa: BLE001
        return ""
    cleaned = " ".join((raw or "").split()).strip().strip('"')
    if 10 <= len(cleaned) <= 600:
        return cleaned
    return ""
