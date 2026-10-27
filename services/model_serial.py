"""Serialize local model loading on a single GPU.

One process-wide slot plus an optional cross-process lock file. Callers wrap
model calls with ``model_slot``; the last user releases the Ollama model via
``keep_alive=0`` so the next model can fit.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

_LOCK = threading.Lock()
_ACTIVE = 0
_LOCK_FILE = Path(os.environ.get("SCIPAL_MODEL_LOCK", "")) if os.environ.get(
    "SCIPAL_MODEL_LOCK"
) else None


def active_count() -> int:
    return _ACTIVE


@contextmanager
def model_slot(name: str = "model", timeout: float = 600.0) -> Iterator[str]:
    global _ACTIVE
    deadline = time.time() + timeout
    acquired = _LOCK.acquire(timeout=timeout)
    if not acquired:
        raise TimeoutError(f"model slot busy: {name}")
    try:
        while _LOCK_FILE and _LOCK_FILE.exists():
            if time.time() > deadline:
                raise TimeoutError(f"model lock busy: {name}")
            time.sleep(0.5)
        if _LOCK_FILE:
            _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            _LOCK_FILE.write_text(name, encoding="utf-8")
        _ACTIVE += 1
        try:
            yield name
        finally:
            _ACTIVE -= 1
            if _LOCK_FILE and _LOCK_FILE.exists():
                _LOCK_FILE.unlink()
    finally:
        _LOCK.release()


def release_ollama(model: str, host: Optional[str] = None) -> None:
    """Ask Ollama to unload a model (best effort)."""
    base = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
    if base.startswith("http://") is False and base.startswith("https://") is False:
        base = f"http://{base}"
    payload = f'{{"model":"{model}","keep_alive":0}}'.encode()
    request = urllib.request.Request(
        f"{base}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=10).read()
    except Exception:  # noqa: BLE001 - unloading is best effort
        pass
