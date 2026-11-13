"""Pure ranking helpers shared by search and tests."""

from __future__ import annotations


def path_weight(query: str, path: str) -> float:
    """Tests are useful only when the question asks for tests/errors."""
    lower = (path or "").lower()
    if "benchmarks/" in lower:
        return 0.55
    if lower.startswith("tests/") or "/tests/" in lower:
        ask = query.lower()
        wants = any(
            phrase in ask
            for phrase in (
                "which test",
                "test verifies",
                "test covers",
                "test compares",
                "pytest",
                "error",
                "failure",
                "assert",
            )
        )
        return 1.10 if wants else 0.55
    return 1.0
