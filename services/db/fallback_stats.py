"""Lightweight in-process PG fallback counters for health visibility."""

from __future__ import annotations

import threading
from collections import Counter
from typing import Dict

_COUNTS: Counter = Counter()
_LOCK = threading.Lock()


def record(component: str) -> None:
    with _LOCK:
        _COUNTS[component] += 1


def snapshot() -> Dict[str, int]:
    with _LOCK:
        return dict(_COUNTS)


def reset() -> None:
    with _LOCK:
        _COUNTS.clear()
