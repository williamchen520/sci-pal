"""Section-level draft/review loop (policy only, no prompts, no LLM client).

The 5-dimension rubric, the 60-point threshold and the "retry once with feedback"
rule live in ``review_generator`` today, mixed with 160 lines of prompt building.
This module isolates the *control flow* so it can be tested with two callables:

- ``generate(feedback: str) -> str`` writes one section draft;
- ``review(text: str) -> (score, note)`` scores it and returns revision notes.

Wiring the real writer (prompt + LLM + sentence splitting) is a separate step;
see ``docs/workflow-runner-design.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

Generate = Callable[[str], str]
Review = Callable[[str], tuple[float, str]]

PASS_THRESHOLD = 60.0


@dataclass(frozen=True)
class SectionAttempt:
    text: str
    score: float
    feedback: str
    attempts: int
    threshold: float = PASS_THRESHOLD

    @property
    def passed(self) -> bool:
        return self.score >= self.threshold


def write_section_loop(
    generate: Generate,
    review: Review,
    *,
    threshold: float = PASS_THRESHOLD,
    max_attempts: int = 2,
) -> SectionAttempt:
    """Draft a section, score it, and retry at most ``max_attempts - 1`` times.

    Returns the best attempt by score (not necessarily the last one): a retry
    can be worse, and shipping the worse draft would be a regression.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    feedback = ""
    best: SectionAttempt | None = None

    for attempt in range(1, max_attempts + 1):
        text = generate(feedback)
        score, note = review(text)
        current = SectionAttempt(
            text=text,
            score=float(score),
            feedback=note,
            attempts=attempt,
            threshold=threshold,
        )
        if best is None or current.score > best.score:
            best = current
        if current.score >= threshold:
            return current
        feedback = note

    assert best is not None  # max_attempts >= 1 guarantees one loop iteration
    return replace(best, attempts=max_attempts)
