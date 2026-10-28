"""Section-type routing for evidence ranking."""

from __future__ import annotations

import re

REFERENCE = re.compile(r"reference|bibliograph|acknowledg|funding|conflict of interest", re.I)
INTRO = re.compile(r"introduction|background", re.I)
METHOD = re.compile(r"method|material|patient|participant|inclusion|exclusion|dose|protocol|statistical", re.I)
RESULT = re.compile(r"result|outcome|efficacy|survival|response|finding|analysis", re.I)
DISCUSSION = re.compile(r"discussion|limitation|implication|conclusion|future", re.I)

RESULT_QUERY = re.compile(
    r"response|survival|orr|pfs|os\b|efficacy|outcome|rate|hazard|p\s*value|how many|"
    r"百分比|生存|缓解|疗效|结局",
    re.I,
)
METHOD_QUERY = re.compile(
    r"method|patient|participant|inclusion|exclusion|dose|protocol|random|sample|"
    r"方法|入组|剂量|随机",
    re.I,
)
DISCUSSION_QUERY = re.compile(
    r"limitation|challenge|future|controvers|discussion|局限|争议|挑战", re.I
)
BACKGROUND_QUERY = re.compile(r"what is|define|background|overview|定义|背景|概述", re.I)


def classify_section(title: str) -> str:
    text = title or ""
    if REFERENCE.search(text):
        return "references"
    if INTRO.search(text):
        return "introduction"
    if METHOD.search(text):
        return "methods"
    if RESULT.search(text):
        return "results"
    if DISCUSSION.search(text):
        return "discussion"
    return "other"


def query_intent(question: str) -> str:
    text = question or ""
    if DISCUSSION_QUERY.search(text):
        return "discussion"
    if METHOD_QUERY.search(text):
        return "methods"
    if RESULT_QUERY.search(text):
        return "results"
    if BACKGROUND_QUERY.search(text):
        return "introduction"
    return "results"


def section_prior(intent: str, section_type: str) -> float:
    if section_type == "references":
        return -1.0
    if section_type == intent:
        return 0.15
    if intent == "results" and section_type == "methods":
        return 0.05
    return 0.0
