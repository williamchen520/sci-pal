"""Pure evidence-row extraction rules (no storage)."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

DESIGN_PATTERNS = [
    ("systematic review", r"systematic review|meta-analysis"),
    ("RCT", r"randomi[sz]ed|randomi[sz]ation"),
    ("cohort", r"cohort study|retrospective cohort|prospective cohort"),
    ("case-control", r"case-control"),
    ("single-arm", r"single-arm|single arm"),
    ("review", r"narrative review|review"),
]
SAMPLE_RE = re.compile(r"(?:n\s*=\s*)?(\d{2,6})\s+(?:patients|participants|subjects|cases|adults)")
EFFECT_RE = re.compile(r"(HR|OR|RR)\s*[=:]?\s*[\d.]+|(\d{1,3}(?:\.\d+)?)\s?%")


def extract_evidence(paper: Dict[str, Any], pico: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    text = f"{paper.get('title') or ''}. {paper.get('abstract') or ''}"
    lower = text.lower()
    design = "unknown"
    for label, pattern in DESIGN_PATTERNS:
        if re.search(pattern, lower):
            design = label
            break
    sample = SAMPLE_RE.search(text)
    effect = EFFECT_RE.search(text)
    pico = pico or {}
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 40]
    outcome_sentence = next(
        (s for s in sentences if re.search(r"outcome|endpoint|response|survival|efficacy", s, re.I)),
        sentences[0] if sentences else "",
    )
    return {
        "design": design,
        "sample_size": sample.group(1) if sample else "",
        "intervention": pico.get("intervention", ""),
        "comparator": pico.get("comparator", ""),
        "outcomes": outcome_sentence[:300],
        "effect": effect.group(0) if effect else "",
        "source_sentence": outcome_sentence[:300],
    }
