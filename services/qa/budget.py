"""Adaptive retrieval budget for QA questions."""

from __future__ import annotations

import os
import re

COMPLEX_MARKERS = re.compile(
    r"(review|overview|landscape|comparison|compare|versus|vs\.?|"
    r"meta-analysis|systematic|across|all studies|evidence|"
    r"综述|比较|对比|全景|所有研究|证据|进展)",
    re.IGNORECASE,
)


def is_complex(question: str) -> bool:
    text = (question or "").strip()
    if len(text) >= 120:
        return True
    if text.count("?") > 1 or text.count("？") > 1:
        return True
    if COMPLEX_MARKERS.search(text):
        return True
    return False


def choose_top_k(
    question: str,
    simple_k: int = 10,
    complex_k: int = 20,
) -> int:
    if os.environ.get("SCIPAL_QA_ADAPTIVE_TOPK") == "0":
        return simple_k
    return complex_k if is_complex(question) else simple_k
