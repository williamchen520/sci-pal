"""Route detected import items into paper/code/quarantine lanes."""

from __future__ import annotations

from dataclasses import dataclass

PAPER_KINDS = frozenset({"jats", "html", "pdf"})
CODE_KINDS = frozenset({"repo", "zip", "python", "r", "rmd"})


@dataclass(frozen=True)
class Route:
    lane: str
    target: str
    reason: str


def route(source_kind: str) -> Route:
    kind = (source_kind or "unknown").strip().lower()
    if kind in PAPER_KINDS:
        return Route("paper", f"{kind}_library", f"{kind} -> paper lane")
    if kind in CODE_KINDS:
        return Route("code", "code_library", f"{kind} -> code lane")
    return Route("quarantine", "quarantine", "unknown -> quarantine")
