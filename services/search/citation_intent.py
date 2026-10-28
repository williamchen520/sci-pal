"""Rule-based citation intent: support / contrast / mention."""

from __future__ import annotations

import re

CONTRAST = re.compile(
    r"(however|in contrast|conversely|unlike|whereas|but |discrepan|conflict|"
    r"contradict|failed to|did not|not consistent|challenge)",
    re.IGNORECASE,
)
SUPPORT = re.compile(
    r"(consistent with|in line with|support|confirm|agree|similar|corroborat|"
    r"accord|in accordance|reproduc)",
    re.IGNORECASE,
)


def classify(text: str) -> str:
    text = text or ""
    if CONTRAST.search(text):
        return "contrast"
    if SUPPORT.search(text):
        return "support"
    return "mention"
