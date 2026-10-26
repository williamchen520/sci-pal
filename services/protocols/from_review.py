"""Draft a protocols.io-style protocol from a generated review.

The draft is intentionally conservative: only sentences that look like method
statements become steps, and nothing is invented -- every step is a sentence
copied from the review body.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

METHOD_KEYWORDS = (
    "incubat", "stain", "antibod", "culture", "treat", "measur", "assay",
    "pcr", "blot", "centrifug", "wash", "transfect", "sirna", "crispr",
    "knockout", "knockdown", "mice", "mouse", "cells were", "samples were",
    "we used", "we performed", "was performed", "were performed", "dose",
    "injected", "isolated", "sequenc", "flow cytometry", "elisa", "stimulat",
)

_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+")
_CITATION = re.compile(r"\[[0-9,\s]+\]")


def _clean(sentence: str) -> str:
    text = re.sub(r"^[#>\-\*\s]+", "", sentence)
    text = _CITATION.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def build_protocol_payload(review: Mapping[str, Any], max_steps: int = 20) -> dict[str, Any]:
    review_id = str(review.get("review_id") or "review")
    topic = str(review.get("topic") or "综述").strip()
    markdown = str(review.get("markdown") or "")
    sentences = [_clean(part) for part in _SENTENCE.split(markdown)]
    steps = [
        sentence
        for sentence in sentences
        if len(sentence) >= 30 and any(key in sentence.lower() for key in METHOD_KEYWORDS)
    ][:max_steps]
    return {
        "protocol": {
            "id": f"review_{review_id}",
            "title": f"{topic}（实验方案草稿）",
            "steps": [
                {
                    "id": f"review_{review_id}_step_{index}",
                    "title": sentence[:80],
                    "step": sentence,
                }
                for index, sentence in enumerate(steps, 1)
            ],
        },
        "source_review_id": review_id,
    }
