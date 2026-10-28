"""Prompt-injection guard for untrusted paper text.

Papers are untrusted input: a PDF/abstract may contain instructions aimed at
the model. We never execute or follow them; detection is used to warn and to
neutralize high-risk phrases before they reach a prompt.
"""

from __future__ import annotations

import re
from typing import Dict, List

PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)",
    r"disregard\s+(the\s+)?(system|previous)\s+(prompt|instructions?)",
    r"(reveal|print|show|repeat)\s+(your\s+)?(system\s+prompt|instructions?)",
    r"you\s+are\s+(now\s+)?(dan|developer\s+mode|jailbroken)",
    r"^\s*(system|assistant)\s*:",
    r"call\s+(the\s+)?tool\s+",
    r"execute\s+(the\s+following\s+)?(python|shell|command|code)",
    r"(exfiltrate|send)\s+.*\s+to\s+https?://",
    r"(reveal|leak)\s+.*(api[_\s-]?key|password|token)",
    r"override\s+(the\s+)?(safety|system|policy)",
    r"jailbreak",
    r"begin\s+system\s+prompt",
]
_COMPILED = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in PATTERNS]

UNTRUSTED_START = "<<UNTRUSTED_EVIDENCE>>"
UNTRUSTED_END = "<<END_UNTRUSTED_EVIDENCE>>"


def find_injections(text: str) -> List[Dict[str, str]]:
    findings = []
    for pattern, regex in zip(PATTERNS, _COMPILED):
        for match in regex.finditer(text or ""):
            findings.append({"pattern": pattern, "match": match.group(0)[:80]})
    return findings


def sanitize(text: str) -> str:
    """Neutralize high-risk phrases while keeping the scientific content."""
    cleaned = text or ""
    for regex in _COMPILED:
        cleaned = regex.sub("[filtered-instruction]", cleaned)
    return cleaned


def wrap_untrusted(text: str) -> str:
    return f"{UNTRUSTED_START}\n{sanitize(text)}\n{UNTRUSTED_END}"


def has_injection(text: str) -> bool:
    return bool(find_injections(text))
